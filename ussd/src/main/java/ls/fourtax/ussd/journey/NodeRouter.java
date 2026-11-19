package ls.fourtax.ussd.journey;

import java.util.*;
import static ls.fourtax.ussd.journey.State.*;
import org.springframework.stereotype.Component;

@Component
public class NodeRouter {
    public List<String> fields(String sector) {
        return RegistrationSchema.fields(sector);
    }
    public List<String> fields(Draft draft) {
        return fields(draft.sector).stream().filter(field -> RegistrationSchema.applies(draft, field)).toList();
    }
    public String fieldNode(Draft draft, String field) {
        if (field.equals("employees") && draft.collections.getOrDefault("employees", List.of()).isEmpty())
            return "FIELD:employees.name";
        return RegistrationSchema.group(draft.sector, field) == null ? "FIELD:" + field : "COLLECTION:" + field;
    }
    public void go(Session session, String node) {
        if (node.equals("COLLECTION:employees") && session.draft != null) node = fieldNode(session.draft, "employees");
        if (!session.node.equals(node)) session.history.add(session.node);
        session.node = node; session.page = 0; session.error = null;
        if (session.draft != null && ((node.startsWith("FIELD:") || node.startsWith("COLLECTION:")) || Set.of("SECTOR", "CONTACT", "DAYS", "OPTIONAL_NAME", "REVIEW", "EDIT").contains(node)))
            session.draft.node = node;
    }
    public void next(Session session, String field) {
        if (session.editing) {
            if (!field.equals("other_description") && RegistrationSchema.requiresOtherDescription(session.draft)
                    && session.draft.answers.getOrDefault("other_description", "").isBlank()) {
                go(session, "FIELD:other_description"); return;
            }
            session.editing = false; go(session, "REVIEW"); return;
        }
        List<String> fields = fields(session.draft.sector);
        int index = fields.indexOf(field) + 1;
        while (index < fields.size() && !RegistrationSchema.applies(session.draft, fields.get(index))) index++;
        go(session, index == fields.size() ? "REVIEW" : fieldNode(session.draft, fields.get(index)));
    }
    public void back(Session session) {
        session.clearPin(); session.error = null; session.page = 0;
        if (session.editing) { session.editing = false; session.node = "EDIT"; return; }
        while (!session.history.isEmpty()) {
            String previous = session.history.removeLast();
            if (previous.startsWith("TX_")) continue; // Transaction navigation has its own stage and confirmation guards.
            if (session.registered && (previous.equals("MAIN") || previous.equals("ENTRY_RETRY"))) continue;
            if (previous.equals("COLLECTION:employees") && session.draft != null
                    && session.draft.collections.getOrDefault("employees", List.of()).isEmpty()) continue;
            if (previous.startsWith("FIELD:") && session.draft != null
                    && !RegistrationSchema.applies(session.draft, previous.substring(6))) continue;
            if (!previous.startsWith("PIN_") && !previous.equals("LOGIN_PIN") && !previous.equals("END")) {
                session.node = previous; return;
            }
        }
        session.node = session.token == null ? (session.registered ? "LOGIN_PIN" : "MAIN") : "AUTH_MENU";
    }
}
