package ls.fourtax.ussd.journey;

import static ls.fourtax.ussd.journey.State.*;
import java.util.*;
import ls.fourtax.ussd.UssdSettings;
import org.springframework.stereotype.Component;

@Component
public class Screen {
    private final Messages messages;
    private final NodeRouter router;
    private final int limit;
    public Screen(Messages messages, NodeRouter router, UssdSettings settings) {
        this.messages = messages; this.router = router; this.limit = settings.screenLimit();
    }
    public List<String> pages(Session s) {
        String body = body(s);
        if (s.error != null) body = messages.text(s.language, s.error) + "\n" + body;
        boolean terminal = s.node.equals("END");
        String footer = terminal || Set.of("LANGUAGE", "MAIN", "LOGIN_PIN").contains(s.node)
                ? "" : "\n" + messages.text(s.language, "navigation");
        if (body.length() + footer.length() <= limit) return List.of(body + footer);
        String paging = "\n" + messages.text(s.language, "pagination");
        int capacity = limit - footer.length() - paging.length() - 12;
        List<String> chunks = new ArrayList<>();
        String rest = body;
        while (!rest.isEmpty()) {
            int end = Math.min(capacity, rest.length());
            if (end < rest.length()) {
                int boundary = rest.lastIndexOf('\n', end);
                if (boundary < 1) boundary = rest.lastIndexOf(' ', end);
                if (boundary > 0) end = boundary;
            }
            chunks.add(rest.substring(0, end)); rest = rest.substring(end).stripLeading();
        }
        List<String> pages = new ArrayList<>();
        for (int i = 0; i < chunks.size(); i++)
            pages.add("(" + (i + 1) + "/" + chunks.size() + ")\n" + chunks.get(i) + paging + footer);
        return pages;
    }
    public String render(Session s) {
        List<String> pages = pages(s); s.page = Math.max(0, Math.min(s.page, pages.size() - 1)); return pages.get(s.page);
    }
    private String body(Session s) {
        if (s.node.startsWith("FIELD:")) return RegistrationSchema.prompt(s.draft.sector, s.node.substring(6), s.language);
        if (s.node.startsWith("COLLECTION:")) {
            String name = s.node.substring(11);
            int count = s.draft.collections.getOrDefault(name, List.of()).size();
            return RegistrationSchema.label(s.draft.sector, name, s.language) + " (" + count + ")\n" + messages.text(s.language, "collectionActions");
        }
        return switch (s.node) {
            case "LANGUAGE" -> messages.text(s.language, "language");
            case "MAIN" -> messages.text(s.language, "main");
            case "AUTH_MENU" -> messages.text(s.language, "authenticated");
            case "SECTOR" -> messages.text(s.language, "sector");
            case "CONTACT" -> messages.text(s.language, "contact", s.mobile);
            case "DAYS" -> messages.text(s.language, "days");
            case "OPTIONAL_NAME" -> messages.text(s.language, "optionalName");
            case "RESUME" -> messages.text(s.language, "resume");
            case "LOGIN_PIN" -> messages.text(s.language, "loginPin");
            case "PIN_NEW" -> messages.text(s.language, "newPin");
            case "PIN_CONFIRM" -> messages.text(s.language, "confirmPin");
            case "AUTH_UNKNOWN" -> messages.text(s.language, "authUnknown");
            case "RETRY" -> messages.text(s.language, "retry");
            case "EDIT" -> edit(s);
            case "REVIEW" -> review(s);
            case "END" -> s.terminal == null ? messages.text(s.language, "goodbye") : s.terminal;
            default -> throw new IllegalStateException("No screen for node " + s.node);
        };
    }
    private String edit(Session s) {
        var text = new StringBuilder(messages.text(s.language, "edit"));
        List<String> fields = router.fields(s.draft);
        for (int i = 0; i < fields.size(); i++) text.append("\n").append(i + 1).append(". ").append(RegistrationSchema.label(s.draft.sector, fields.get(i), s.language));
        return text.toString();
    }
    private String review(Session s) {
        var text = new StringBuilder(messages.text(s.language, "review"));
        for (String field : router.fields(s.draft)) {
            var group = RegistrationSchema.group(s.draft.sector, field);
            if (group == null) text.append("\n").append(RegistrationSchema.label(s.draft.sector, field, s.language)).append(": ")
                    .append(RegistrationSchema.display(s.draft.sector, field, s.draft.answers.get(field), s.language));
            else {
                var rows = s.draft.collections.getOrDefault(field, List.of());
                if (rows.isEmpty()) text.append("\n").append(RegistrationSchema.label(s.draft.sector, field, s.language)).append(": 0");
                // Every row already labels its fields. A separate heading can become a content-free page.
                for (int i = 0; i < rows.size(); i++) {
                    text.append("\n").append(i + 1).append(". ");
                    var values = new ArrayList<String>();
                    for (var item : group.get("fields")) {
                        String key = item.get("name").asText();
                        values.add(RegistrationSchema.label(s.draft.sector, field + "." + key, s.language) + ": "
                                + RegistrationSchema.display(s.draft.sector, field + "." + key, rows.get(i).get(key), s.language));
                    }
                    text.append(String.join(" / ", values));
                }
            }
        }
        return text.append("\n").append(messages.text(s.language, "reviewActions")).toString();
    }
}
