package ls.fourtax.ussd.callback;

import ls.fourtax.ussd.journey.Messages;
import ls.fourtax.ussd.api.ApiTrace;
import tools.jackson.databind.json.JsonMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class XmlCallbackController {
    private final SessionCoordinator coordinator;
    private final GrapevineXml xml = new GrapevineXml();
    private final Messages messages;
    private final ApiTrace trace;
    private final JsonMapper json;
    public XmlCallbackController(SessionCoordinator coordinator, Messages messages, ApiTrace trace, JsonMapper json) {
        this.coordinator = coordinator; this.messages = messages; this.trace = trace; this.json = json;
    }
    @PostMapping(value = "/ussd/callback/grapevine", consumes = {"application/xml", "text/xml"}, produces = "application/xml;charset=UTF-8")
    void callback(HttpServletRequest request, HttpServletResponse response) throws IOException {
        // Read/write directly: Spring MVC debug body logging must not capture PIN XML or review screens.
        String body = new String(request.getInputStream().readNBytes(16_385), StandardCharsets.UTF_8);
        String reply = xml.render(coordinator.handle(xml.parse(body)));
        response.setContentType("application/xml;charset=UTF-8"); response.getWriter().write(reply);
    }
    // Explicit developer endpoint; the gateway authentication and journey are identical.
    // Manual I/O prevents MVC body logging. Nothing survives this request on the server.
    @PostMapping(value = "/ussd/callback/grapevine/inspect", consumes = {"application/xml", "text/xml"}, produces = "application/json")
    void inspect(HttpServletRequest request, HttpServletResponse response) throws IOException {
        try (var capture = trace.begin()) {
            String body = new String(request.getInputStream().readNBytes(16_385), StandardCharsets.UTF_8);
            String reply = xml.render(coordinator.handle(xml.parse(body)));
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write(json.writeValueAsString(java.util.Map.of("responseXml", reply, "exchanges", capture.exchanges())));
        }
    }
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> invalid() { return ResponseEntity.badRequest().contentType(MediaType.APPLICATION_XML)
            .body(xml.render(new Callback.Reply("Invalid gateway request.", true))); }
    @ExceptionHandler({IllegalStateException.class, org.springframework.dao.DataAccessException.class})
    ResponseEntity<String> unavailable() { return ResponseEntity.status(503).contentType(MediaType.APPLICATION_XML)
            .body(xml.render(new Callback.Reply(messages.text("en", "busy"), true))); }
}
