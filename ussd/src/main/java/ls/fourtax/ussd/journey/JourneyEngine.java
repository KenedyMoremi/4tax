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
        if (s.draft != null && s.draft.sector != null && !RegistrationSchema.sectors().contains(s.draft.sector)
                && !s.node.equals("RESUME")) { router.go(s, "RESUME"); s.error = "error.oldDraft"; return; }
        if (skipInactiveDescription(s)) return;
        if (input.equals("0")) {
            if (s.draft != null && s.draft.mayHaveSubmitted) { router.go(s, "RETRY"); return; }
            router.back(s); return;
        }
        int count = screens.pages(s).size();
        if (count > 1 && (input.equals("88") || input.equals("87"))) {
            s.page = Math.max(0, Math.min(count - 1, s.page + (input.equals("88") ? 1 : -1))); return;
        }
        s.error = null; s.page = 0;
        if (s.node.startsWith("COLLECTION:")) { collection(s, s.node.substring(11), input); return; }
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
    public void enforceAccess(Session s) {
        if (!s.node.equals("END") && authorized(s)) {
            skipInactiveDescription(s);
            if (s.node.equals("COLLECTION:employees") && !s.draft.mayHaveSubmitted
                    && s.draft.collections.getOrDefault("employees", List.of()).isEmpty()) {
                router.go(s, "FIELD:employees.name"); save(s);
            }
        }
    }
    private boolean skipInactiveDescription(Session s) {
        if (!s.node.startsWith("FIELD:") && !s.node.startsWith("COLLECTION:")
                && !Set.of("REVIEW", "EDIT").contains(s.node)) return false;
        if (s.draft == null || s.draft.sector == null || !RegistrationSchema.sectors().contains(s.draft.sector)
                || RegistrationSchema.requiresOtherDescription(s.draft) || s.draft.mayHaveSubmitted) return false;
        boolean changed = s.draft.answers.containsKey("other_description")
                && !"".equals(s.draft.answers.get("other_description"));
        if (changed) s.draft.answers.put("other_description", "");
        boolean skipped = s.node.equals("FIELD:other_description");
        if (skipped) router.next(s, "other_description");
        if (changed || skipped) save(s);
        return skipped;
    }

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
        if (s.draft.sector != null && !RegistrationSchema.sectors().contains(s.draft.sector)) { router.go(s, "RESUME"); s.error = "error.oldDraft"; return; }
        String next = s.draft.node;
        if (Set.of("RESUME", "RETRY", "AUTH_UNKNOWN", "SUBMIT").contains(next)) next = "REVIEW";
        router.go(s, next);
    }
    private void sector(Session s, String input) {
        int index;
        try { index = Integer.parseInt(input) - 1; } catch (NumberFormatException e) { invalid(s); return; }
        var sectors = RegistrationSchema.sectors();
        if (index < 0 || index >= sectors.size()) { invalid(s); return; }
        String sector = sectors.get(index);
        if (!sector.equals(s.draft.sector)) { s.draft.answers.clear(); s.draft.collections.clear(); s.draft.operationId = UUID.randomUUID().toString(); }
        s.draft.sector = sector; router.go(s, router.fieldNode(s.draft, router.fields(sector).getFirst())); save(s);
    }
    private void collection(Session s, String name, String input) {
        var group = RegistrationSchema.group(s.draft.sector, name);
        var rows = s.draft.collections.computeIfAbsent(name, k -> new ArrayList<>());
        if (input.equals("1") && rows.size() < group.get("maximum").asInt()) {
            s.draft.answers.keySet().removeIf(k -> k.startsWith(name + "."));
            router.go(s, "FIELD:" + name + "." + group.get("fields").get(0).get("name").asText());
        } else if (input.equals("2") && rows.size() >= group.get("minimum").asInt()) {
            s.draft.answers.put(name, Integer.toString(rows.size())); router.next(s, name);
        } else if (input.equals("3")) {
            rows.clear(); s.draft.answers.remove(name);
            s.draft.answers.keySet().removeIf(key -> key.startsWith(name + "."));
            router.go(s, "COLLECTION:" + name);
        } else { invalid(s); return; }
        save(s);
    }
    private void field(Session s, String field, String input) {
        String value = input.strip().replaceAll("\\s+", " ");
        if (field.equals("employees.name") && value.equals("-")) {
            int count = s.draft.collections.getOrDefault("employees", List.of()).size();
            if (count < RegistrationSchema.group(s.draft.sector, "employees").get("minimum").asInt()) { invalid(s); return; }
            s.draft.answers.keySet().removeIf(key -> key.startsWith("employees."));
            s.draft.answers.put("employees", Integer.toString(count));
            router.next(s, "employees"); save(s); return;
        }
        if (field.equals("other_description") && RegistrationSchema.requiresOtherDescription(s.draft)
                && (value.isBlank() || value.equals("-"))) { s.error = "error.otherDescriptionRequired"; return; }
        try {
            if (value.chars().anyMatch(Character::isISOControl)) throw new IllegalArgumentException();
            value = RegistrationSchema.parse(s.draft.sector, field, value);
        } catch (IllegalArgumentException e) { invalid(s); return; }
        s.draft.answers.put(field, value);
        if (field.contains(".")) {
            String groupName = field.substring(0, field.indexOf('.'));
            var fields = RegistrationSchema.group(s.draft.sector, groupName).get("fields");
            int index = 0;
            while (!(groupName + "." + fields.get(index).get("name").asText()).equals(field)) index++;
            if (index + 1 < fields.size()) {
                router.go(s, "FIELD:" + groupName + "." + fields.get(index + 1).get("name").asText());
            } else {
                var row = new LinkedHashMap<String, String>();
                for (var f : fields) {
                    String key = f.get("name").asText(); row.put(key, s.draft.answers.remove(groupName + "." + key));
                }
                s.draft.collections.computeIfAbsent(groupName, k -> new ArrayList<>()).add(row);
                router.go(s, "COLLECTION:" + groupName);
                s.history.removeIf(n -> n.startsWith("FIELD:" + groupName + "."));
            }
        } else router.next(s, field);
        save(s);
    }
    private void review(Session s, String input) {
        if (input.equals("2")) {
            if (s.draft.mayHaveSubmitted) s.error = "error.retryFirst"; else router.go(s, "EDIT"); return;
        }
        if (!input.equals("1")) { invalid(s); return; }
        // An ambiguous submission must keep its original payload until the API confirms its result.
        if (s.draft.mayHaveSubmitted) { submit(s); return; }
        for (String field : router.fields(s.draft)) {
            if (!s.draft.answers.containsKey(field) || (field.equals("other_description") && s.draft.answers.get(field).isBlank())) {
                if (field.equals("other_description")) s.editing = true;
                router.go(s, router.fieldNode(s.draft, field)); save(s); return;
            }
        }
        if (s.token == null) router.go(s, "PIN_NEW"); else submit(s);
    }
    private void edit(Session s, String input) {
        try {
            int index = Integer.parseInt(input) - 1;
            List<String> fields = router.fields(s.draft);
            if (index < 0 || index >= fields.size()) throw new IllegalArgumentException();
            s.editing = true; router.go(s, router.fieldNode(s.draft, fields.get(index))); save(s);
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
                continueDraft(s);
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
                if (failure.code.equals("VALIDATION_ERROR") || failure.code.equals("CONFLICT") || failure.code.equals("PAYLOAD_TOO_LARGE")) {
                    s.draft.mayHaveSubmitted = false; save(s);
                }
                router.go(s, "RETRY");
                s.error = failure.code.equals("PAYLOAD_TOO_LARGE") ? "error.payloadTooLarge" : failure.code.equals("VALIDATION_ERROR") ? "error.validation"
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
        var details = new LinkedHashMap<String, Object>();
        for (String field : router.fields(s.draft.sector)) {
            if (!Set.of("fullNames", "idNumber").contains(field) && RegistrationSchema.group(s.draft.sector, field) == null)
                details.put(field, RegistrationSchema.value(s.draft.sector, field, field.equals("other_description") ? a.getOrDefault(field, "") : a.get(field)));
        }
        return new BusinessRegistration(s.draft.sector, new Owner(a.get("idNumber"), a.get("fullNames")), details,
                s.draft.collections.getOrDefault("employees", List.of()),
                s.draft.sector.equals("transport") ? s.draft.collections.getOrDefault("routes", List.of()) : null,
                s.draft.sector.equals("agriculture") ? s.draft.collections.getOrDefault("livestock", List.of()) : null,
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
