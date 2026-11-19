package ls.fourtax.ussd.journey;

import static ls.fourtax.ussd.journey.State.*;
import static ls.fourtax.ussd.api.Contracts.*;
import java.time.*;
import java.util.*;
import ls.fourtax.ussd.api.Backend;
import ls.fourtax.ussd.session.SessionStore;
import org.springframework.stereotype.Component;

@Component
public class JourneyEngine {
    private static final List<String> WEEK = List.of("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY");
    private final NodeRouter router;
    private final Backend backend;
    private final SessionStore store;
    private final Crypto crypto;
    private final Messages messages;
    private final Screen screens;

    public JourneyEngine(NodeRouter router, Backend backend, SessionStore store, Crypto crypto, Messages messages, Screen screens) {
        this.router = router; this.backend = backend; this.store = store; this.crypto = crypto; this.messages = messages; this.screens = screens;
    }

    public void input(Session s, String input) {
        if (input.equals("99")) { end(s, "goodbye"); return; }
        if (!authorized(s)) return;
        if (input.equals("0")) {
            if (s.draft != null && s.draft.mayHaveSubmitted) { router.go(s, "RETRY"); return; }
            router.back(s); return;
        }
        int count = screens.pages(s).size();
        if (count > 1 && (input.equals("88") || input.equals("87"))) {
            s.page = Math.max(0, Math.min(count - 1, s.page + (input.equals("88") ? 1 : -1))); return;
        }
        s.error = null;
        if (s.node.startsWith("FIELD:")) { field(s, s.node.substring(6), input); return; }
        switch (s.node) {
            case "LANGUAGE" -> {
                if (!List.of("1", "2").contains(input)) { invalid(s); return; }
                s.language = input.equals("1") ? "en" : "st"; router.go(s, "MAIN");
            }
            case "MAIN" -> {
                if (input.equals("1")) begin(s);
                else if (input.equals("2")) { s.resumeAfterLogin = false; router.go(s, "LOGIN_PIN"); }
                else invalid(s);
            }
            case "AUTH_MENU" -> { if (input.equals("1")) begin(s); else invalid(s); }
            case "RESUME" -> resume(s, input);
            case "SECTOR" -> sector(s, input);
            case "OPTIONAL_NAME" -> {
                if (input.equals("1")) router.go(s, "FIELD:businessName");
                else if (input.equals("2")) { s.draft.answers.remove("businessName"); router.next(s, "businessName"); save(s); }
                else invalid(s);
            }
            case "CONTACT" -> {
                if (input.equals("1")) { s.draft.answers.put("mobileNumber", s.mobile); router.next(s, "mobileNumber"); save(s); }
                else if (input.equals("2")) router.go(s, "FIELD:mobileNumber");
                else invalid(s);
            }
            case "DAYS" -> days(s, input);
            case "REVIEW" -> review(s, input);
            case "EDIT" -> edit(s, input);
            case "PIN_NEW" -> newPin(s, input);
            case "PIN_CONFIRM" -> confirmPin(s, input);
            case "LOGIN_PIN" -> login(s, input);
            case "RETRY" -> {
                if (input.equals("1")) submit(s);
                else if (input.equals("2")) {
                    if (s.draft.mayHaveSubmitted) s.error = "error.retryFirst";
                    else { s.draft.operationId = UUID.randomUUID().toString(); router.go(s, "EDIT"); save(s); }
                }
                else invalid(s);
            }
            case "AUTH_UNKNOWN" -> {
                if (input.equals("1")) router.go(s, "PIN_NEW");
                else if (input.equals("2")) { s.resumeAfterLogin = true; router.go(s, "LOGIN_PIN"); }
                else invalid(s);
            }
            default -> invalid(s);
        }
    }

    private boolean authorized(Session s) {
        boolean needsOwner = Node.of(s.node).access() == Node.Access.OWNER
                || (s.draft != null && s.draft.ownerId != null && !Set.of("LOGIN_PIN", "RESUME", "MAIN", "LANGUAGE").contains(s.node));
        if (!needsOwner) return true;
        try {
            if (s.token == null || s.tokenExpiry <= Instant.now().getEpochSecond()) throw new Backend.Failure("LOGIN_REQUIRED");
            String ownerId = backend.verifyOwner(s.token);
            if (!ownerId.equals(s.ownerId) || (s.draft != null && s.draft.ownerId != null && !ownerId.equals(s.draft.ownerId)))
                throw new Backend.Failure("LOGIN_REQUIRED");
            return true;
        } catch (Backend.Failure failure) {
            s.clearAuthentication(); s.resumeAfterLogin = s.draft != null; router.go(s, "LOGIN_PIN"); s.error = "error.expired"; return false;
        }
    }
    public void enforceAccess(Session s) { if (!s.node.equals("END")) authorized(s); }

    private void begin(Session s) {
        Draft draft = store.draft(crypto.digest(s.mobile));
        if (draft != null) { s.draft = draft; router.go(s, "RESUME"); return; }
        fresh(s);
    }
    private void fresh(Session s) {
        s.draft = new Draft(); s.draft.language = s.language; s.draft.ownerId = s.ownerId;
        s.draft.authenticationStarted = s.ownerId != null;
        s.editing = false; router.go(s, "SECTOR"); save(s);
    }
    private void resume(Session s, String input) {
        if (input.equals("2")) { store.deleteDraft(crypto.digest(s.mobile)); fresh(s); return; }
        if (!input.equals("1")) { invalid(s); return; }
        if (s.draft.authenticationStarted && s.token == null) {
            s.resumeAfterLogin = true; router.go(s, "LOGIN_PIN");
        } else continueDraft(s);
    }
    private void continueDraft(Session s) {
        if (s.draft.ownerId != null && !s.draft.ownerId.equals(s.ownerId)) { end(s, "error.expired"); return; }
        String next = s.draft.node;
        if (Set.of("RESUME", "RETRY", "AUTH_UNKNOWN", "SUBMIT").contains(next)) next = "REVIEW";
        router.go(s, next);
    }
    private void sector(Session s, String input) {
        String sector = switch (input) { case "1" -> "TRANSPORT"; case "2" -> "WELLNESS"; case "3" -> "VENDOR"; default -> null; };
        if (sector == null) { invalid(s); return; }
        if (!sector.equals(s.draft.sector)) { s.draft.answers.clear(); s.draft.operationId = UUID.randomUUID().toString(); }
        s.draft.sector = sector; router.go(s, router.fieldNode(s.draft, router.fields(sector).getFirst())); save(s);
    }
    private void field(Session s, String field, String input) {
        String value = input.strip().replaceAll("\\s+", " ");
        if (value.isBlank() || value.length() > (field.equals("location") || field.equals("residence") ? 120 : 80)
                || value.chars().anyMatch(Character::isISOControl)) { invalid(s); return; }
        try {
            value = switch (field) {
                case "mobileNumber" -> PhoneNumbers.normalize(value);
                case "opensAt", "closesAt" -> {
                    if (!value.matches("(?:[01][0-9]|2[0-3]):[0-5][0-9]")) throw new IllegalArgumentException();
                    yield value;
                }
                case "days" -> parseDays(value);
                case "vin", "numberPlate" -> {
                    if (!value.matches("[A-Za-z0-9 -]{1,32}")) throw new IllegalArgumentException();
                    yield value.toUpperCase(Locale.ROOT);
                }
                case "idNumber" -> {
                    if (!value.matches("[A-Za-z0-9 -]{1,64}")) throw new IllegalArgumentException(); yield value;
                }
                default -> value;
            };
        } catch (IllegalArgumentException error) { invalid(s); return; }
        s.draft.answers.put(field, value); router.next(s, field); save(s);
    }
    private String parseDays(String input) {
        LinkedHashSet<String> selected = new LinkedHashSet<>();
        for (String day : input.split(",", -1)) {
            if (!day.strip().matches("[1-7]")) throw new IllegalArgumentException();
            selected.add(WEEK.get(Integer.parseInt(day.strip()) - 1));
        }
        return String.join(",", WEEK.stream().filter(selected::contains).toList());
    }
    private void days(Session s, String input) {
        String days = switch (input) {
            case "1" -> String.join(",", WEEK.subList(0, 5));
            case "2" -> String.join(",", WEEK.subList(0, 6));
            case "3" -> String.join(",", WEEK);
            default -> null;
        };
        if (input.equals("4")) { router.go(s, "FIELD:days"); return; }
        if (days == null) { invalid(s); return; }
        s.draft.answers.put("days", days); router.next(s, "days"); save(s);
    }
    private void review(Session s, String input) {
        if (input.equals("2")) {
            if (s.draft.mayHaveSubmitted) s.error = "error.retryFirst"; else router.go(s, "EDIT"); return;
        }
        if (!input.equals("1")) { invalid(s); return; }
        for (String field : router.fields(s.draft.sector)) {
            if (field.equals("businessName") && !s.draft.sector.equals("WELLNESS")) continue;
            if (!s.draft.answers.containsKey(field)) { router.go(s, router.fieldNode(s.draft, field)); return; }
        }
        if (s.token == null) router.go(s, "PIN_NEW"); else submit(s);
    }
    private void edit(Session s, String input) {
        try {
            int index = Integer.parseInt(input) - 1;
            List<String> fields = router.fields(s.draft.sector);
            if (index < 0 || index >= fields.size()) throw new IllegalArgumentException();
            s.editing = true; router.go(s, router.fieldNode(s.draft, fields.get(index)));
        } catch (IllegalArgumentException error) { invalid(s); }
    }
    private void newPin(Session s, String pin) {
        if (!pin.matches("[0-9]{6}")) { s.error = "error.pinFormat"; return; }
        s.pinNonce = UUID.randomUUID().toString(); s.pinDigest = crypto.digest(s.pinNonce + ":" + pin);
        router.go(s, "PIN_CONFIRM");
    }
    private void confirmPin(Session s, String pin) {
        if (!pin.matches("[0-9]{6}")) { s.error = "error.pinFormat"; return; }
        boolean matches = crypto.matches(s.pinDigest, s.pinNonce + ":" + pin); s.clearPin();
        if (!matches) { router.go(s, "PIN_NEW"); s.error = "error.pinMismatch"; return; }
        s.draft.authenticationStarted = true; save(s);
        try {
            authenticate(s, backend.createOwner(s.mobile, pin, s.draft.operationId));
            s.draft.ownerId = s.ownerId; save(s); submit(s);
        } catch (Backend.Failure failure) {
            if (failure.code.equals("OWNER_EXISTS")) {
                s.resumeAfterLogin = true; router.go(s, "LOGIN_PIN"); s.error = "error.ownerExists";
            } else { router.go(s, "AUTH_UNKNOWN"); s.error = "error.unavailable"; }
        }
    }
    private void login(Session s, String pin) {
        if (!pin.matches("[0-9]{6}")) { s.error = "error.pinFormat"; return; }
        try {
            authenticate(s, backend.login(s.mobile, pin));
            if (s.resumeAfterLogin && s.draft != null) {
                s.draft.ownerId = s.ownerId; save(s); s.resumeAfterLogin = false;
                router.go(s, s.draft.sector == null ? "SECTOR" : "REVIEW");
            } else { s.draft = null; router.go(s, "AUTH_MENU"); }
        } catch (Backend.Failure failure) {
            s.error = failure.code.equals("PIN_LOCKED") ? "error.locked"
                    : failure.code.equals("SERVICE_UNAVAILABLE") ? "error.unavailable" : "error.login";
        }
    }
    private void authenticate(Session s, TokenReply reply) {
        String subject = backend.verifyOwner(reply.accessToken());
        if (!subject.equals(reply.ownerId()) || (s.draft != null && s.draft.ownerId != null && !subject.equals(s.draft.ownerId)))
            throw new Backend.Failure("LOGIN_REQUIRED");
        s.token = reply.accessToken(); s.ownerId = subject;
        s.tokenExpiry = Instant.now().getEpochSecond() + Math.min(reply.expiresIn(), 900);
    }
    private void submit(Session s) {
        if (!authorizedForSubmission(s)) return;
        // Persist the operation before I/O. A lost response is retried with this same key.
        s.draft.node = "REVIEW"; s.draft.mayHaveSubmitted = true; save(s);
        try {
            RegistrationReply reply = backend.register(s.token, registration(s), s.draft.operationId);
            store.deleteDraft(crypto.digest(s.mobile)); s.draft = null;
            s.terminal = messages.text(s.language, "success", reply.reference()); s.node = "END"; s.clearAuthentication();
        } catch (Backend.Failure failure) {
            if (failure.code.equals("LOGIN_REQUIRED")) {
                s.clearAuthentication(); s.resumeAfterLogin = true; router.go(s, "LOGIN_PIN"); s.error = "error.expired";
            } else {
                if (failure.code.equals("VALIDATION_ERROR") || failure.code.equals("CONFLICT")) {
                    s.draft.mayHaveSubmitted = false; save(s);
                }
                router.go(s, "RETRY");
                s.error = failure.code.equals("VALIDATION_ERROR") ? "error.validation"
                        : failure.code.equals("CONFLICT") || failure.code.equals("IDEMPOTENCY_CONFLICT") ? "error.conflict" : "error.unavailable";
            }
        }
    }
    private boolean authorizedForSubmission(Session s) {
        try {
            if (s.token == null || s.tokenExpiry <= Instant.now().getEpochSecond() || !backend.verifyOwner(s.token).equals(s.ownerId))
                throw new Backend.Failure("LOGIN_REQUIRED");
            return true;
        } catch (Backend.Failure failure) {
            s.clearAuthentication(); s.resumeAfterLogin = true; router.go(s, "LOGIN_PIN"); s.error = "error.expired"; return false;
        }
    }
    BusinessRegistration registration(Session s) {
        Map<String, String> a = s.draft.answers;
        return new BusinessRegistration(Sector.valueOf(s.draft.sector), new Owner(a.get("idNumber"), a.get("fullNames"), a.get("residence")),
                a.get("businessName"), a.get("mobileNumber"), a.get("location"),
                s.draft.sector.equals("TRANSPORT") ? new Vehicle(a.get("vin"), a.get("numberPlate")) : null,
                s.draft.sector.equals("WELLNESS") ? new Schedule(List.of(a.get("days").split(",")), a.get("opensAt"), a.get("closesAt")) : null,
                new Source("USSD", s.draft.language));
    }
    private void save(Session s) {
        if (s.draft != null) {
            store.saveDraft(crypto.digest(s.mobile), s.draft);
        }
    }
    private void invalid(Session s) { s.error = "error.invalid"; }
    public void end(Session s, String key) { s.terminal = messages.text(s.language, key); s.node = "END"; s.clearAuthentication(); }
}
