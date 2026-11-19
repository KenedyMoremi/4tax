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
                int boundary = Math.max(rest.lastIndexOf('\n', end), rest.lastIndexOf(' ', end));
                if (boundary > capacity / 2) end = boundary;
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
        if (s.node.startsWith("FIELD:")) return messages.text(s.language, "prompt." + s.node.substring(6));
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
        List<String> fields = router.fields(s.draft.sector);
        for (int i = 0; i < fields.size(); i++) text.append("\n").append(i + 1).append(". ").append(messages.text(s.language, "label." + fields.get(i)));
        return text.toString();
    }
    private String review(Session s) {
        var text = new StringBuilder(messages.text(s.language, "review"));
        for (String field : router.fields(s.draft.sector)) {
            String value = s.draft.answers.getOrDefault(field, messages.text(s.language, "omitted"));
            if (field.equals("days") && s.draft.answers.containsKey(field)) {
                value = String.join(", ", Arrays.stream(value.split(",")).map(day -> messages.text(s.language, "day." + day)).toList());
            }
            text.append("\n").append(messages.text(s.language, "label." + field)).append(": ").append(value);
        }
        return text.append("\n").append(messages.text(s.language, "reviewActions")).toString();
    }
}
