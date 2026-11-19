package ls.fourtax.ussd.callback;

import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.*;

@RestController
@Profile("dev")
public class SimulatorController {
    private final SessionCoordinator coordinator;
    public SimulatorController(SessionCoordinator coordinator) { this.coordinator = coordinator; }
    @PostMapping("/ussd/callback/simulator")
    Callback.Reply callback(@RequestBody Callback request) {
        return coordinator.handle(new Callback("simulator", request.network(), request.sessionId(), request.mobileNumber(),
                request.event(), request.input(), request.serviceCode(), request.requestId()));
    }
}
