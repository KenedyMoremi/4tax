package ls.fourtax.mock;

import static ls.fourtax.mock.Contracts.*;
import java.util.*;
import org.springframework.http.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

/** Deliberately in-memory, synthetic development substitute for the external business system. */
@RestController
public class RegistrationController {
    private final Map<String, Saved> entries = new HashMap<>();
    @PostMapping("/api/v1/businesses")
    synchronized ResponseEntity<?> create(@AuthenticationPrincipal Jwt owner,
            @RequestHeader(value = "Idempotency-Key", defaultValue = "") String key,
            @RequestBody BusinessRegistration request) {
        if (!key.matches("[A-Za-z0-9._:-]{1,128}")) return error(400, "INVALID_IDEMPOTENCY_KEY");
        String identity = owner.getSubject() + ":" + key;
        Saved saved = entries.get(identity);
        if (saved != null) return saved.request().equals(request) ? ResponseEntity.ok(saved.reply()) : error(409, "IDEMPOTENCY_CONFLICT");
        if (!valid(request)) return error(422, "VALIDATION_ERROR");
        String id = UUID.randomUUID().toString();
        var reply = new RegistrationReply(id, "DEMO-" + id.substring(0, 8).toUpperCase(Locale.ROOT));
        entries.put(identity, new Saved(request, reply));
        return ResponseEntity.status(201).body(reply);
    }
    private boolean valid(BusinessRegistration r) {
        if (r == null || r.sector() == null || r.owner() == null || empty(r.owner().idNumber()) || empty(r.owner().fullNames())
                || r.source() == null || !"USSD".equals(r.source().channel()) || r.source().language() == null
                || !Set.of("en", "st").contains(r.source().language())) return false;
        return switch (r.sector()) {
            case TRANSPORT -> r.vehicle() != null && !empty(r.vehicle().vin()) && !empty(r.vehicle().numberPlate()) && !empty(r.owner().residence());
            case VENDOR -> !empty(r.location()) && mobile(r.mobileNumber());
            case WELLNESS -> !empty(r.businessName()) && !empty(r.location()) && mobile(r.mobileNumber()) && schedule(r.operatingSchedule());
        };
    }
    private boolean schedule(Schedule s) {
        return s != null && s.days() != null && !s.days().isEmpty()
                && s.days().stream().allMatch(day -> day != null && Set.of("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY").contains(day))
                && time(s.opensAt()) && time(s.closesAt());
    }
    private boolean time(String t) { return t != null && t.matches("(?:[01][0-9]|2[0-3]):[0-5][0-9]"); }
    private boolean mobile(String s) { return s != null && s.matches("\\+[1-9][0-9]{7,14}"); }
    private boolean empty(String s) { return s == null || s.isBlank() || s.length() > 120; }
    private ResponseEntity<ApiError> error(int status, String code) { return ResponseEntity.status(status).body(new ApiError(code, "Synthetic registration rejected.")); }
    private record Saved(BusinessRegistration request, RegistrationReply reply) {}
}
