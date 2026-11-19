package ls.fourtax.ussd.callback;

import ls.fourtax.ussd.journey.Messages;
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
    public XmlCallbackController(SessionCoordinator coordinator, Messages messages) { this.coordinator = coordinator; this.messages = messages; }
    @PostMapping(value = "/ussd/callback/grapevine", consumes = {"application/xml", "text/xml"}, produces = "application/xml;charset=UTF-8")
    void callback(HttpServletRequest request, HttpServletResponse response) throws IOException {
        // Read/write directly: Spring MVC debug body logging must not capture PIN XML or review screens.
        String body = new String(request.getInputStream().readNBytes(16_385), StandardCharsets.UTF_8);
        String reply = xml.render(coordinator.handle(xml.parse(body)));
        response.setContentType("application/xml;charset=UTF-8"); response.getWriter().write(reply);
    }
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> invalid() { return ResponseEntity.badRequest().contentType(MediaType.APPLICATION_XML)
            .body(xml.render(new Callback.Reply("Invalid gateway request.", true))); }
    @ExceptionHandler({IllegalStateException.class, org.springframework.dao.DataAccessException.class})
    ResponseEntity<String> unavailable() { return ResponseEntity.status(503).contentType(MediaType.APPLICATION_XML)
            .body(xml.render(new Callback.Reply(messages.text("en", "busy"), true))); }
}
