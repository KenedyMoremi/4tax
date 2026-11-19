package ls.fourtax.ussd.callback;

import static ls.fourtax.ussd.callback.Callback.*;
import java.util.Objects;
import ls.fourtax.ussd.journey.*;
import ls.fourtax.ussd.journey.State.*;
import ls.fourtax.ussd.session.SessionStore;
import org.springframework.stereotype.Service;
import tools.jackson.databind.json.JsonMapper;

@Service
public class SessionCoordinator {
    private final SessionStore store;
    private final JourneyEngine engine;
    private final Screen screen;
    private final Crypto crypto;
    private final Messages messages;
    private final JsonMapper json;
    public SessionCoordinator(SessionStore store, JourneyEngine engine, Screen screen, Crypto crypto, Messages messages, JsonMapper json) {
        this.store = store; this.engine = engine; this.screen = screen; this.crypto = crypto; this.messages = messages; this.json = json;
    }
    public Reply handle(Callback callback) {
        if (callback == null || callback.event() == null || blank(callback.sessionId()) || blank(callback.network())
                || callback.sessionId().length() > 128 || callback.network().length() > 32 || blank(callback.adapter())
                || callback.adapter().length() > 32 || (callback.input() != null && callback.input().length() > 256)
                || (callback.requestId() != null && callback.requestId().length() > 128))
            throw new IllegalArgumentException("Invalid callback");
        String mobile = PhoneNumbers.normalize(callback.mobileNumber());
        String callerKey = crypto.digest(mobile);
        String key = crypto.digest(callback.adapter() + ":" + callback.network() + ":" + callback.sessionId() + ":" + mobile);
        return store.locked(key, callerKey, () -> process(callback, mobile, callerKey, key));
    }
    private Reply process(Callback callback, String mobile, String callerKey, String key) {
        String requestKey = callback.requestId() == null || callback.requestId().isBlank() ? null
                : key + ":" + crypto.digest(callback.requestId());
        if (requestKey != null) {
            String cached = store.cached(requestKey);
            if (cached != null) return json.readValue(cached, Reply.class);
        }
        Session session = callback.event() == Event.START ? new Session(mobile) : store.session(key);
        if (session == null) return new Reply(messages.text("en", "error.sessionExpired"), true);
        if (callback.event() == Event.ABORT) {
            session.clearAuthentication(); store.deleteSession(key);
            return new Reply(messages.text(session.language, "goodbye"), true);
        }
        if (callback.event() == Event.INPUT) {
            if (session.draft != null) {
                Draft current = store.draft(callerKey);
                if (current == null || !Objects.equals(current.operationId, session.draft.operationId)) engine.end(session, "error.sessionExpired");
                else session.draft = current;
            }
            if (!session.node.equals("END")) engine.input(session, Objects.requireNonNullElse(callback.input(), ""));
        }
        engine.enforceAccess(session);
        Reply reply = new Reply(screen.render(session), session.node.equals("END"));
        if (reply.end()) { session.clearAuthentication(); store.deleteSession(key); }
        else store.saveSession(key, session);
        if (requestKey != null) store.cache(requestKey, json.writeValueAsString(reply));
        return reply;
    }
    private boolean blank(String value) { return value == null || value.isBlank(); }
}
