package ls.fourtax.emulator;

import static ls.fourtax.emulator.Contracts.*;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/emulator")
public class EmulatorController {
    private final IdentityGenerator generator;
    private final CallbackRelay relay;
    private final EmulatorSettings settings;
    public EmulatorController(IdentityGenerator generator, CallbackRelay relay, EmulatorSettings settings) {
        this.generator = generator; this.relay = relay; this.settings = settings;
    }
    @GetMapping("/config") Map<String, Object> config() {
        return Map.of("callbackUrl", settings.defaultCallbackUrl(), "serviceCode", settings.defaultServiceCode(),
                "network", "VOD", "mcc", "651", "mnc", "01", "prefix", "58");
    }
    @PostMapping("/identities") List<Subscriber> identities(@RequestBody GeneratorRequest request) { return generator.generate(request); }
    @PostMapping("/exchanges") ResponseEntity<ExchangeReply> exchange(@RequestBody ExchangeRequest request) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(relay.exchange(request));
    }
    @ExceptionHandler(IllegalArgumentException.class) ResponseEntity<ApiError> invalid(IllegalArgumentException error) {
        return ResponseEntity.badRequest().body(new ApiError("INVALID_REQUEST", error.getMessage()));
    }
}
