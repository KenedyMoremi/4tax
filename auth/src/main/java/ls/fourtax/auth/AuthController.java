package ls.fourtax.auth;

import static ls.fourtax.auth.Contracts.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {
    private final OwnerAuthService auth;
    public AuthController(OwnerAuthService auth) { this.auth = auth; }
    @PostMapping("/owners/lookup")
    ResponseEntity<OwnerStatus> lookup(@RequestBody OwnerLookup request) {
        return ResponseEntity.ok().cacheControl(org.springframework.http.CacheControl.noStore()).body(auth.lookup(request));
    }
    @PostMapping("/owners")
    ResponseEntity<TokenReply> create(@RequestBody PinRequest request,
            @RequestHeader(value = "Idempotency-Key", required = false) String key) {
        return ResponseEntity.status(201).cacheControl(org.springframework.http.CacheControl.noStore()).body(auth.create(request, key));
    }
    @PostMapping("/pin/login")
    ResponseEntity<TokenReply> login(@RequestBody PinRequest request) {
        return ResponseEntity.ok().cacheControl(org.springframework.http.CacheControl.noStore()).body(auth.login(request));
    }
    @ExceptionHandler(OwnerAuthService.AuthFailure.class)
    ResponseEntity<ApiError> failure(OwnerAuthService.AuthFailure failure) {
        return ResponseEntity.status(failure.status).body(new ApiError(failure.code, "Authentication request could not be completed."));
    }
}
