package ls.fourtax.ussd.journey;

import java.util.*;
import java.math.BigDecimal;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Generated metadata comes from the Django forms; no network dependency per screen. */
public final class RegistrationSchema {
    private static final JsonNode ROOT;
    static {
        try (var input = RegistrationSchema.class.getResourceAsStream("/registration-schema.json")) {
            ROOT = JsonMapper.builder().build().readTree(input);
        } catch (Exception e) { throw new IllegalStateException("Missing registration schema", e); }
    }
    public static List<String> sectors() {
        var result = new ArrayList<String>();
        ROOT.get("sectors").forEach(s -> result.add(s.get("value").asText())); return result;
    }
    static JsonNode sector(String name) {
        for (var s : ROOT.get("sectors")) if (s.get("value").asText().equals(name)) return s;
        throw new IllegalArgumentException("Unknown sector");
    }
    public static List<String> fields(String name) {
        var result = new ArrayList<String>();
        var fields = sector(name).get("fields");
        result.add(fields.get(0).get("name").asText());
        result.add("fullNames"); result.add("idNumber");
        for (int i=1; i<fields.size(); i++) result.add(fields.get(i).get("name").asText());
        for (var group : sector(name).get("collections")) result.add(group.get("name").asText());
        return result;
    }
    public static JsonNode group(String sector, String name) {
        for (var group : sector(sector).get("collections")) if (group.get("name").asText().equals(name)) return group;
        return null;
    }
    public static JsonNode field(String sector, String name) {
        if (name.contains(".")) {
            String[] parts = name.split("\\.");
            for (var f : group(sector, parts[0]).get("fields")) if (f.get("name").asText().equals(parts[1])) return f;
        }
        for (var f : ROOT.get("ownerFields")) if (f.get("name").asText().equals(name)) return f;
        for (var f : sector(sector).get("fields")) if (f.get("name").asText().equals(name)) return f;
        throw new IllegalArgumentException("Unknown field");
    }
    public static String label(String sector, String name, String language) {
        var group = group(sector, name);
        return new Messages().text(language, "registration.field." + name);
    }
    public static String prompt(String sector, String name, String language) {
        var f = field(sector, name);
        var messages = new Messages();
        var result = new StringBuilder(label(sector, name, language));
        String type = f.get("type").asText();
        if (type.equals("boolean")) return result + "\n1. " + messages.text(language, "registration.yes") + "\n2. " + messages.text(language, "registration.no");
        if (f.has("choices")) {
            if (type.equals("multiple_choice")) result.append(messages.text(language, "registration.commas"));
            int index = 1;
            for (var choice : f.get("choices")) result.append("\n").append(index++).append(". ").append(messages.text(language, "registration.choice." + choice.get("value").asText()));
        } else if (type.equals("time")) result.append(" (HH:MM)");
        else if (type.equals("integer") || type.equals("decimal")) result.append(messages.text(language, "registration.zero"));
        else if (!f.get("required").asBoolean()) result.append(messages.text(language, "registration.skip"));
        return result.toString();
    }
    public static String parse(String sector, String name, String input) {
        var f = field(sector, name);
        String type = f.get("type").asText();
        if (input.equals("-") && !f.get("required").asBoolean()) return "";
        if (type.equals("boolean")) {
            if (!Set.of("1","2").contains(input)) throw new IllegalArgumentException();
            return input.equals("1") ? "true" : "false";
        }
        if (f.has("choices")) {
            var selected = new ArrayList<String>();
            String[] numbers = type.equals("multiple_choice") ? input.split(",", -1) : new String[]{input};
            for (String n : numbers) {
                int index = Integer.parseInt(n.strip()) - 1;
                if (index < 0 || index >= f.get("choices").size()) throw new IllegalArgumentException();
                String value = f.get("choices").get(index).get("value").asText();
                if (selected.contains(value)) throw new IllegalArgumentException();
                selected.add(value);
            }
            return String.join(",", selected);
        }
        if (type.equals("time") && !input.matches("(?:[01][0-9]|2[0-3]):[0-5][0-9]")) throw new IllegalArgumentException();
        if (type.equals("integer") || type.equals("decimal")) {
            if (!input.matches(type.equals("integer") ? "[0-9]{1,7}" : "[0-9]{1,10}(\\.[0-9]{1,4})?")) throw new IllegalArgumentException();
            BigDecimal value = new BigDecimal(input);
            if (f.has("decimal_places") && Math.max(value.scale(),0) > Integer.parseInt(f.get("decimal_places").asText())) throw new IllegalArgumentException();
            if (f.has("min_value") && value.compareTo(new BigDecimal(f.get("min_value").asText())) < 0) throw new IllegalArgumentException();
            if (f.has("max_value") && value.compareTo(new BigDecimal(f.get("max_value").asText())) > 0) throw new IllegalArgumentException();
            return value.toPlainString();
        }
        if (input.isBlank() || input.length() > (f.has("max_length") ? Integer.parseInt(f.get("max_length").asText()) : 250)) throw new IllegalArgumentException();
        return input;
    }
    public static Object value(String sector, String name, String value) {
        String type = field(sector, name).get("type").asText();
        if (type.equals("boolean")) return Boolean.valueOf(value);
        if (type.equals("multiple_choice")) return List.of(value.split(","));
        return value;
    }
}
