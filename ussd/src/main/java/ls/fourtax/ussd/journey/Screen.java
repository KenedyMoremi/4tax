package ls.fourtax.ussd.journey;

import static ls.fourtax.ussd.journey.State.*;
import java.util.*;
import ls.fourtax.ussd.UssdSettings;
import org.springframework.stereotype.Component;

/** Rendering and accepted commands share the same page definition. */
@Component
public class Screen {
    public record Page(String text, Map<String, String> commands, boolean input) {}
    private record Choice(String label, String value) {}
    private static final class Content {
        String text;
        boolean input;
        final List<Choice> choices = new ArrayList<>();
        final Map<String, Choice> actions = new LinkedHashMap<>();
        Content(String text) { this.text = text; }
    }
    private static final class Part {
        String text = "";
        final Map<String, String> commands = new LinkedHashMap<>();
        int choices;
    }
    private final Messages messages;
    private final NodeRouter router;
    private final int limit;
    public Screen(Messages messages, NodeRouter router, UssdSettings settings) {
        this.messages = messages; this.router = router; this.limit = settings.screenLimit();
    }
    private String m(Session s, String key) { return messages.text(s.language, key); }
    static boolean canExit(Session s) { return !Set.of("END","LANGUAGE","MAIN","LOGIN_PIN").contains(s.node); }
    private void action(Content c, Session s, String key, String label, String value) {
        c.actions.put(key, new Choice(m(s, label), value));
    }
    public List<String> pages(Session s) { return layout(s).stream().map(Page::text).toList(); }
    public Page current(Session s) {
        var pages = layout(s); s.page = Math.clamp(s.page, 0, pages.size()-1); return pages.get(s.page);
    }
    public String render(Session s) { return current(s).text(); }
    public List<Page> layout(Session s) {
        Content c = content(s);
        if (s.error != null) c.text = m(s, s.error) + "\n" + c.text;
        boolean exit = canExit(s);
        boolean back = exit && !(s.draft != null && s.draft.mayHaveSubmitted)
                && !(s.transaction != null && s.transaction.frozen);
        String backValue = s.node.equals("TX_BUSINESS") && s.businessPage > 1 ? "@businessPrevious" : "@back";
        StringBuilder actions = new StringBuilder();
        c.actions.forEach((key, choice) -> actions.append('\n').append(key).append(". ").append(choice.label));
        StringBuilder single = new StringBuilder(c.text);
        var singleCommands = new LinkedHashMap<String,String>();
        for (int i=0;i<c.choices.size();i++) {
            if (!single.isEmpty()) single.append('\n');
            single.append(i+1).append(". ").append(c.choices.get(i).label);
            singleCommands.put(Integer.toString(i+1),c.choices.get(i).value);
        }
        single.append(actions); c.actions.forEach((key,choice)->singleCommands.put(key,choice.value));
        if(back) { single.append("\n8. ").append(m(s,"nav.back")); singleCommands.put("8",backValue); }
        if(exit) { single.append("\n0. ").append(m(s,"nav.exit")); singleCommands.put("0","@exit"); }
        if(single.length()<=limit && c.choices.size()<=(c.actions.containsKey("7")?6:7))
            return List.of(new Page(single.toString(),Map.copyOf(singleCommands),c.input));
        // Reserve room for page numbers, both directions, exit and final-page actions.
        int capacity = limit - 12 - ("\n8. " + m(s, "nav.back") + "\n9. " + m(s, "nav.next")
                + (exit ? "\n0. " + m(s, "nav.exit") : "")).length() - actions.length();
        if (capacity < 16) throw new IllegalStateException("Screen controls exceed configured limit");
        var parts = new ArrayList<Part>(); parts.add(new Part());
        append(parts, c.text, c.choices.isEmpty()?capacity:Math.max(16,capacity-16));
        for (var choice : c.choices) {
            Part part = parts.getLast();
            int maximum = c.actions.containsKey("7") ? 6 : 7;
            if (part.choices == maximum || (part.choices>0 && part.text.length() + choice.label.length() + 4 > capacity)) {
                part = new Part(); parts.add(part);
            }
            // A long business/field label can span pages, retaining its selectable value.
            String remaining = choice.label;
            do {
                part = parts.getLast();
                String key = Integer.toString(++part.choices);
                int room = capacity - part.text.length() - (part.text.isEmpty()?3:4);
                if(room<1) { part=new Part(); parts.add(part); key=Integer.toString(++part.choices); room=capacity-3; }
                int end = boundary(remaining, room);
                if (!part.text.isEmpty()) part.text += "\n";
                part.text += key + ". " + remaining.substring(0, end);
                part.commands.put(key, choice.value);
                remaining = remaining.substring(end).stripLeading();
                if (!remaining.isEmpty()) parts.add(new Part());
            } while (!remaining.isEmpty());
        }
        var result = new ArrayList<Page>();
        for (int i=0; i<parts.size(); i++) {
            Part part = parts.get(i);
            var commands = new LinkedHashMap<>(part.commands);
            String text = (parts.size() > 1 ? "(" + (i+1) + "/" + parts.size() + ")\n" : "") + part.text;
            if (i == parts.size()-1) {
                text += actions;
                c.actions.forEach((key, choice) -> commands.put(key, choice.value));
            } else {
                text += "\n9. " + m(s, "nav.next"); commands.put("9", "@next");
            }
            if (i > 0 || back) {
                text += "\n8. " + m(s, "nav.back"); commands.put("8", i > 0 ? "@previous" : backValue);
            }
            if (exit) { text += "\n0. " + m(s, "nav.exit"); commands.put("0", "@exit"); }
            if (text.length() > limit) throw new IllegalStateException("Screen exceeds configured limit");
            result.add(new Page(text, Map.copyOf(commands), c.input));
        }
        return result;
    }
    private static int boundary(String value, int capacity) {
        int end = Math.min(capacity, value.length());
        if (end < value.length()) {
            int split = value.lastIndexOf('\n', end);
            if (split < capacity/2) split = value.lastIndexOf(' ', end);
            if (split > 0) end = split;
        }
        return end;
    }
    private static void append(List<Part> parts, String value, int capacity) {
        String rest = value;
        while (!rest.isEmpty()) {
            int end = boundary(rest, capacity);
            parts.getLast().text = rest.substring(0, end);
            rest = rest.substring(end).stripLeading();
            if (!rest.isEmpty()) parts.add(new Part());
        }
    }
    private Content menu(Session s, String key) {
        String[] lines = m(s, key).split("\n");
        var title = new ArrayList<String>(); var c = new Content("");
        for (String line : lines) {
            if (line.matches("[1-7]\\. .*")) c.choices.add(new Choice(line.substring(3), line.substring(0,1)));
            else title.add(line);
        }
        c.text = String.join("\n", title); return c;
    }
    private Content content(Session s) {
        if (s.node.startsWith("TX_")) return transaction(s);
        if (s.node.startsWith("FIELD:")) {
            String name = s.node.substring(6);
            var f = RegistrationSchema.field(s.draft.sector, name);
            Content c;
            if (name.equals("overnight")) {
                c = new Content(m(s, "registration.overnightPrompt"));
                action(c,s,"1","nav.correctTimes","@correctTimes"); action(c,s,"9","nav.confirmOvernight","1");
            } else if (f.has("choices") && !f.get("type").asText().equals("multiple_choice")) {
                c = new Content(RegistrationSchema.label(s.draft.sector,name,s.language)); int i=1;
                for (var choice : f.get("choices")) c.choices.add(new Choice(m(s,"registration.choice."+choice.get("value").asText()),Integer.toString(i++)));
            } else { c = new Content(RegistrationSchema.prompt(s.draft.sector,name,s.language)); c.input=true; }
            if (RegistrationSchema.canSkip(s.draft,name)) action(c,s,"7","nav.skip","@skip");
            return c;
        }
        if (s.node.startsWith("COLLECTION:")) {
            String name=s.node.substring(11); var group=RegistrationSchema.group(s.draft.sector,name);
            int count=s.draft.collections.getOrDefault(name,List.of()).size();
            var c=new Content(RegistrationSchema.label(s.draft.sector,name,s.language)+" ("+count+")");
            if (count<group.get("maximum").asInt()) action(c,s,"1","nav.addAnother","1");
            if (count>0) action(c,s,"2","nav.clear","3");
            if (count>=RegistrationSchema.minimum(s.draft,name)) action(c,s,"9","nav.continue","2");
            return c;
        }
        if (s.node.equals("EDIT")) {
            var c=new Content(m(s,"edit")); int i=1;
            for (String field:router.fields(s.draft)) c.choices.add(new Choice(RegistrationSchema.label(s.draft.sector,field,s.language),Integer.toString(i++)));
            return c;
        }
        if (s.node.equals("REVIEW")) {
            var c=new Content(review(s));
            if (!s.draft.mayHaveSubmitted) action(c,s,"1","nav.edit","2");
            action(c,s,"9","nav.confirm","1"); return c;
        }
        if (s.node.equals("RETRY")) {
            var c=new Content(m(s,"retry"));
            if (!s.draft.mayHaveSubmitted) action(c,s,"1","nav.edit","2");
            action(c,s,"9","nav.retry","1"); return c;
        }
        if (s.node.equals("RESUME")) {
            var c=new Content(m(s,"resume"));
            boolean old=s.draft.sector!=null && !RegistrationSchema.sectors().contains(s.draft.sector);
            if ((!s.draft.authenticationStarted || s.token!=null) && !s.draft.mayHaveSubmitted) action(c,s,"2","nav.discard","2");
            if (!old) action(c,s,"9","nav.resume","1"); return c;
        }
        return switch(s.node) {
            case "LANGUAGE" -> menu(s,"language"); case "MAIN" -> menu(s,"main");
            case "ENTRY_RETRY" -> menu(s,"entryRetry"); case "AUTH_MENU" -> menu(s,"authenticated");
            case "SECTOR" -> menu(s,"sector"); case "AUTH_UNKNOWN" -> menu(s,"authUnknown");
            case "PIN_NEW", "PIN_CONFIRM", "LOGIN_PIN" -> {
                var c=new Content(m(s,s.node.equals("PIN_NEW")?"newPin":s.node.equals("PIN_CONFIRM")?"confirmPin":"loginPin")); c.input=true; yield c;
            }
            case "END" -> new Content(s.terminal==null?m(s,"goodbye"):s.terminal);
            default -> throw new IllegalStateException("No screen for node "+s.node);
        };
    }
    private Content transaction(Session s) {
        var d=s.transaction;
        if (s.node.startsWith("TX_FIELD:")) {
            var c=new Content(TransactionJourney.screen(s,messages)); c.input=true;
            if (s.node.equals("TX_FIELD:buyer")) action(c,s,"7","nav.skip","@skip"); return c;
        }
        if (s.node.equals("TX_BUSINESS") || s.node.equals("TX_EDIT")) {
            var c=new Content(m(s,s.node.equals("TX_BUSINESS")?"tx.chooseBusiness":"edit")); int i=1;
            if (s.node.equals("TX_BUSINESS")) {
                for (var b:s.businesses) {
                    String label=b.businessName()==null||b.businessName().isBlank()?b.reference():b.businessName();
                    c.choices.add(new Choice(m(s,"tx.sector."+b.sector())+" / "+label,Integer.toString(i++)));
                }
                if(s.nextBusinessPage!=null) action(c,s,"9","nav.moreBusinesses","@businessNext");
            } else {
                for(String name:TransactionJourney.fields(d.business.sector())) c.choices.add(new Choice(m(s,"tx.field."+name),Integer.toString(i++)));
                if(d.fields.keySet().containsAll(TransactionJourney.fields(d.business.sector()))) action(c,s,"9","nav.preview","@prepare");
            }
            return c;
        }
        var c=new Content(TransactionJourney.screen(s,messages));
        switch(s.node) {
            case "TX_PREVIEW" -> { action(c,s,"1","nav.edit","@edit"); action(c,s,"2","nav.cancel","2"); action(c,s,"9","nav.post","1"); }
            case "TX_RESUME" -> { if(!d.frozen) action(c,s,"2","nav.discard","2"); action(c,s,"9","nav.resume","1"); }
            case "TX_RETRY", "TX_LOAD", "TX_EMPTY" -> action(c,s,"9","nav.retry","1");
            case "TX_DONE" -> action(c,s,"1","nav.addTransaction","1");
            default -> throw new IllegalStateException("No transaction screen for "+s.node);
        }
        return c;
    }
    private String review(Session s) {
        var text=new StringBuilder(m(s,"review"));
        for(String field:router.fields(s.draft)) {
            var group=RegistrationSchema.group(s.draft.sector,field);
            if(group==null) text.append('\n').append(RegistrationSchema.label(s.draft.sector,field,s.language)).append(": ")
                    .append(RegistrationSchema.display(s.draft.sector,field,s.draft.answers.get(field),s.language));
            else {
                var rows=s.draft.collections.getOrDefault(field,List.of());
                if(rows.isEmpty()) text.append('\n').append(RegistrationSchema.label(s.draft.sector,field,s.language)).append(": 0");
                for(int i=0;i<rows.size();i++) {
                    var row=rows.get(i); text.append('\n').append(m(s,"review."+field)).append(' ').append(i+1).append(": ");
                    text.append(switch(field) {
                        case "routes" -> row.get("origin")+" → "+row.get("destination")+", M"+row.get("price");
                        case "employees" -> row.get("name")+", "+RegistrationSchema.display(s.draft.sector,"employees.salary_range",row.get("salary_range"),s.language)+m(s,"review.monthly");
                        case "livestock" -> row.get("animal_type")+": "+row.get("number");
                        default -> throw new IllegalStateException("Unknown collection");
                    });
                }
            }
        }
        return text.toString();
    }
}
