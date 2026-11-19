package ls.fourtax.emulator;

import static org.junit.jupiter.api.Assertions.*;
import java.net.URI;
import java.net.http.*;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {"emulator.localhost-alias=", "logging.level.root=WARN"})
class EmulatorHttpTest {
    @LocalServerPort int port;
    HttpClient client = HttpClient.newHttpClient();
    @Test void servesTheWorkbenchAndSelfContainedConfiguration() throws Exception {
        var page = client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/")).GET().build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, page.statusCode()); assertTrue(page.body().contains("USSD emulator")); assertTrue(page.body().contains("reply-form"));
        var config = client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/api/emulator/config")).GET().build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, config.statusCode()); assertTrue(config.body().contains("callbackUrl")); assertFalse(config.body().contains("gatewayKey"));
    }
    @Test void exposesGeneratorAndReturnsUsefulValidationErrors() throws Exception {
        var url = URI.create("http://localhost:" + port + "/api/emulator/identities");
        var valid = client.send(HttpRequest.newBuilder(url).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{\"count\":2,\"prefix\":\"58\",\"mnc\":\"01\"}")).build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, valid.statusCode()); assertTrue(valid.body().contains("65101"));
        var invalid = client.send(HttpRequest.newBuilder(url).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{\"count\":500,\"prefix\":\"58\",\"mnc\":\"01\"}")).build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(400, invalid.statusCode()); assertTrue(invalid.body().contains("INVALID_REQUEST"));
    }
}
