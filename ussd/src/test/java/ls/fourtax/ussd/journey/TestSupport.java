package ls.fourtax.ussd.journey;

import static ls.fourtax.ussd.api.Contracts.*;
import java.util.*;
import java.util.function.Supplier;
import ls.fourtax.ussd.UssdSettings;
import ls.fourtax.ussd.api.Backend;
import ls.fourtax.ussd.callback.*;
import ls.fourtax.ussd.journey.State.*;
import ls.fourtax.ussd.session.SessionStore;
import tools.jackson.databind.json.JsonMapper;

public final class TestSupport {
    public static UssdSettings settings() { return new UssdSettings("gateway-key-for-tests-123456789", "state-secret-for-tests-123456789012345", 160, 900,
            "http://localhost:9000", "http://localhost:9000", "http://localhost:9000/oauth2/jwks", "test", "test", "https://registration.example.test"); }
    public static class MemoryStore implements SessionStore {
        final Map<String, String> values = new HashMap<>();
        final Map<String, Long> expiry = new HashMap<>();
        long now;
        final JsonMapper json = JsonMapper.builder().build();
        @Override public synchronized <T> T locked(String key, String mobile, Supplier<T> work) { return work.get(); }
        @Override public Session session(String key) { return get("session:" + key, Session.class); }
        @Override public void saveSession(String key, Session s) { put("session:" + key, s); }
        @Override public void deleteSession(String key) { values.remove("session:" + key); }
        @Override public Draft draft(String mobile) { return get("draft:" + mobile, Draft.class); }
        @Override public void saveDraft(String mobile, Draft draft) { put("draft:" + mobile, draft); }
        @Override public void deleteDraft(String mobile) { values.remove("draft:" + mobile); }
        @Override public TransactionDraft transaction(String mobile) { return get("transaction:"+mobile, TransactionDraft.class); }
        @Override public void saveTransaction(String mobile, TransactionDraft value) { put("transaction:"+mobile, value); }
        @Override public void deleteTransaction(String mobile) { values.remove("transaction:"+mobile); }
        @Override public String cached(String key) { return values.get("reply:" + key); }
        @Override public void cache(String key, String value) { values.put("reply:" + key, value); }
        private <T> T get(String key, Class<T> type) {
            String value = values.get(key); return value == null || expiry.getOrDefault(key, 0L) <= now ? null : json.readValue(value, type);
        }
        private void put(String key, Object value) { values.put(key, json.writeValueAsString(value)); expiry.put(key, now + 900); }
        public String serialized() { return values.toString(); }
        public void advance(long seconds) { now += seconds; }
    }
    public static class FakeBackend implements Backend {
        public int creations;
        public boolean loseRegistrationReply;
        public String failure;
        public final List<String> attempts = new ArrayList<>();
        public final Map<String, BusinessRegistration> saved = new LinkedHashMap<>();
        public final List<BusinessSummary> ownedBusinesses = new ArrayList<>();
        public final Map<String, TransactionRequest> transactionRequests = new LinkedHashMap<>();
        public final List<String> transactionAttempts = new ArrayList<>();
        public final Set<String> postedTransactions = new HashSet<>();
        public String lookupFailure;
        public String transactionFailure;
        public boolean loseTransactionReply;
        public boolean expiredConfirmation;
        public String transactionTotal="200.00";
        final Map<String, String> pins = new HashMap<>();
        @Override public boolean ownerExists(String mobile) { if (lookupFailure != null) throw new Failure(lookupFailure); return pins.containsKey(mobile); }
        @Override public BusinessPage businesses(String token, int page) {
            int from = Math.min((page-1)*5, ownedBusinesses.size()), end = Math.min(from+5, ownedBusinesses.size());
            return new BusinessPage(new ArrayList<>(ownedBusinesses.subList(from,end)), end < ownedBusinesses.size() ? page+1 : null);
        }
        @Override public TransactionReply proposeTransaction(String token, TransactionRequest request, String key) {
            transactionAttempts.add(key);
            if (transactionFailure != null) throw new Failure(transactionFailure);
            var previous = transactionRequests.putIfAbsent(key, request);
            if (previous != null && !previous.equals(request)) throw new Failure("IDEMPOTENCY_CONFLICT");
            if (loseTransactionReply) { loseTransactionReply = false; throw new Failure("SERVICE_UNAVAILABLE"); }
            return new TransactionReply("txn-1", "pending", "TESTPREVIEW1", "Paid sale\nDate: 2026-11-19\nGoods\nTotal: M 200.00\nPayment account: Cash", "",
                    new TransactionPreview("sale", "Goods", "2026-11-19", transactionTotal, "0.00", transactionTotal, request.fields().get("buyer"), "1000", null));
        }
        @Override public TransactionReply resolveTransaction(String token, TransactionAction request, String key) {
            transactionAttempts.add(key);
            if (transactionFailure != null) throw new Failure(transactionFailure);
            if(request.action().equals("cancel") && postedTransactions.contains(key)) throw new Failure("ALREADY_POSTED");
            if(request.action().equals("confirm") && expiredConfirmation) { expiredConfirmation=false; throw new Failure("PROPOSAL_EXPIRED_OR_CHANGED"); }
            if (request.action().equals("confirm")) postedTransactions.add(key);
            if (loseTransactionReply) { loseTransactionReply = false; throw new Failure("SERVICE_UNAVAILABLE"); }
            return new TransactionReply("txn-1", request.action().equals("confirm") ? "posted" : "cancelled", "TESTPREVIEW1", "Sale", "Recorded");
        }
        @Override public TokenReply createOwner(String mobile, String pin, String key) {
            if (pins.containsKey(mobile)) throw new Failure("OWNER_EXISTS");
            pins.put(mobile, pin); creations++; return token();
        }
        @Override public TokenReply login(String mobile, String pin) {
            if (!pin.equals(pins.get(mobile))) throw new Failure("INVALID_CREDENTIALS"); return token();
        }
        TokenReply token() { return new TokenReply("owner-1", "owner-token", "Bearer", 900); }
        @Override public String verifyOwner(String token) {
            if (!"owner-token".equals(token)) throw new Failure("LOGIN_REQUIRED"); return "owner-1";
        }
        @Override public RegistrationReply register(String token, BusinessRegistration request, String key) {
            attempts.add(key);
            if (failure != null) throw new Failure(failure);
            if (saved.containsKey(key) && !saved.get(key).equals(request)) throw new Failure("IDEMPOTENCY_CONFLICT");
            saved.putIfAbsent(key, request);
            if (loseRegistrationReply) { loseRegistrationReply = false; throw new Failure("SERVICE_UNAVAILABLE"); }
            return new RegistrationReply("entity-" + saved.size(), "DEMO-0001");
        }
    }
    public static class Driver {
        public final FakeBackend backend;
        public final SessionStore store;
        public final SessionCoordinator coordinator;
        public final Crypto crypto = new Crypto(settings());
        public String sessionId = UUID.randomUUID().toString();
        public String mobile = "+26658123456";
        public Callback.Reply last;
        int sequence;
        public Driver(SessionStore store, FakeBackend backend) {
            this.store = store; this.backend = backend;
            var router = new NodeRouter(); var messages = new Messages(); var screen = new Screen(messages, router, settings());
            var engine = new JourneyEngine(router, backend, store, crypto, messages, screen);
            coordinator = new SessionCoordinator(store, engine, screen, crypto, messages, JsonMapper.builder().build());
        }
        public Callback.Reply start() { sessionId = UUID.randomUUID().toString(); return send(Callback.Event.START, "", "start"); }
        public Callback.Reply input(String input) { return send(Callback.Event.INPUT, input, "step-" + sequence++); }
        public Callback.Reply send(Callback.Event event, String input, String id) {
            last = coordinator.handle(new Callback("test", "TEST", sessionId, mobile, event, input, "*123#", id));
            if (last.message().length() > 160) throw new AssertionError("Screen exceeds limit");
            return last;
        }
        public Session state() { return store.session(crypto.digest("test:TEST:" + sessionId + ":" + mobile)); }
        public void steps(String... inputs) { for (String input : inputs) input(input); }
        public Screen screens() { return new Screen(new Messages(),new NodeRouter(),settings()); }
        public void lastPage() {
            for(int i=0;i<100 && state().page<screens().pages(state()).size()-1;i++) input("9");
        }
        public void advance() { lastPage(); input("9"); }
        public void choose(String logical) {
            for(int i=0;i<100;i++) {
                var page=screens().current(state());
                for(var entry:page.commands().entrySet()) if(entry.getValue().equals(logical)) { input(entry.getKey()); return; }
                if(!"@next".equals(page.commands().get("9"))) throw new AssertionError("Choice not on menu: "+logical);
                input("9");
            }
            throw new AssertionError("Menu did not terminate");
        }
        public void editField(String name) { lastPage(); input("1"); choose(Integer.toString(new NodeRouter().fields(state().draft).indexOf(name)+1)); }
        public void transportToReview(String language) {
            start(); steps(language, "1", "1"); fillToReview();
        }
        public void vendorFields() { input("4"); fillToReview(); }
        public void fillToReview() { fillUntil("REVIEW"); }
        public void fillUntil(String target) { fillUntilAny(Set.of(target)); }
        public void fillUntilAny(Set<String> targets) {
            for (int step=0; step<100 && !targets.contains(state().node); step++) {
                String node = state().node;
                if (node.startsWith("COLLECTION:")) {
                    String group = node.substring(11);
                    int minimum = RegistrationSchema.group(state().draft.sector, group).get("minimum").asInt();
                    input(state().draft.collections.getOrDefault(group, List.of()).size() < Math.max(minimum, 2) ? "1" : "9");
                } else if (node.startsWith("FIELD:")) {
                    String name = node.substring(6);
                    var field = RegistrationSchema.field(state().draft.sector, name);
                    String value = switch(name) {
                        case "fullNames" -> "Mpho Example";
                        case "idNumber" -> "000123456789";
                        case "vin" -> "VIN00000000000001";
                        case "license_plate" -> "A1234";
                        case "location", "routes.origin" -> "Maseru";
                        case "routes.destination" -> "Roma";
                        case "routes.price" -> "25.50";
                        case "employees.name" -> "Synthetic Employee";
                        case "livestock.animal_type" -> "Cattle";
                        case "livestock.number" -> "12";
                        case "opens_at" -> "08:00";
                        case "closes_at" -> "17:00";
                        case "overnight" -> "2";
                        case "other_description" -> "Synthetic other business";
                        default -> "1";
                    };
                    if(field.has("choices") && !field.get("type").asText().equals("multiple_choice")) choose(value);
                    else input(value);
                } else throw new AssertionError("Unexpected node: " + node);
            }
            if (!targets.contains(state().node)) throw new AssertionError("Did not reach " + targets + "; stopped at " + state().node);
        }
    }
}
