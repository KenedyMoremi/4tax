package ls.fourtax.ussd.session;

import java.util.function.Supplier;
import ls.fourtax.ussd.journey.State.*;

public interface SessionStore {
    <T> T locked(String sessionKey, String mobile, Supplier<T> work);
    Session session(String key);
    void saveSession(String key, Session session);
    void deleteSession(String key);
    Draft draft(String mobile);
    void saveDraft(String mobile, Draft draft);
    void deleteDraft(String mobile);
    TransactionDraft transaction(String mobile);
    void saveTransaction(String mobile, TransactionDraft draft);
    void deleteTransaction(String mobile);
    String cached(String key);
    void cache(String key, String value);
}
