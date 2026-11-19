package ls.fourtax.ussd.journey;

import java.util.*;
import static ls.fourtax.ussd.journey.State.*;
import org.springframework.stereotype.Component;

@Component
public class NodeRouter {
    public List<String> fields(String sector) {
        return RegistrationSchema.fields(sector);
    }
    public String fieldNode(Draft draft, String field) {
        return RegistrationSchema.group(draft.sector, field) == null ? "FIELD:" + field : "COLLECTION:" + field;
    }
    public void go(Session session, String node) {
        if (!session.node.equals(node)) session.history.add(session.node);
        session.node = node; session.page = 0; session.error = null;
        if (session.draft != null && ((node.startsWith("FIELD:") || node.startsWith("COLLECTION:")) || Set.of("SECTOR", "CONTACT", "DAYS", "OPTIONAL_NAME", "REVIEW", "EDIT").contains(node)))
            session.draft.node = node;
    }
    public void next(Session session, String field) {
        if (session.editing) { session.editing = false; go(session, "REVIEW"); return; }
        List<String> fields = fields(session.draft.sector);
        int index = fields.indexOf(field) + 1;
        go(session, index == fields.size() ? "REVIEW" : fieldNode(session.draft, fields.get(index)));
    }
    public void back(Session session) {
        session.clearPin(); session.error = null; session.page = 0;
        if (session.editing) { session.editing = false; session.node = "EDIT"; return; }
        while (!session.history.isEmpty()) {
            String previous = session.history.removeLast();
            if (!previous.startsWith("PIN_") && !previous.equals("LOGIN_PIN") && !previous.equals("END")) {
                session.node = previous; return;
            }
        }
        session.node = session.token == null ? "MAIN" : "AUTH_MENU";
    }
}
