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
    @Test void exchangeApiBindsInspectionAndPreservesBothSidesOfTheCallback() throws Exception {
        var callback = com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1", 0), 0);
        callback.createContext("/ussd/callback/grapevine/inspect", exchange -> {
            exchange.getRequestBody().readAllBytes();
            byte[] body = tools.jackson.databind.json.JsonMapper.builder().build().writeValueAsBytes(Map.of(
                    "responseXml", CallbackRelayTest.GOOD, "exchanges", java.util.List.of(Map.of("stage", "create-owner", "httpStatus", 201))));
            exchange.getResponseHeaders().set("Content-Type", "application/json"); exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body); exchange.close();
        });
        callback.start();
        try {
            var r = GrapevineCodecTest.request("http://127.0.0.1:" + callback.getAddress().getPort() + "/ussd/callback/grapevine",
                    Contracts.Event.START, "", Contracts.NumberFormat.INTERNATIONAL, true, 120);
            var inspected = new Contracts.ExchangeRequest(r.callbackUrl(), r.gatewayHeader(), r.gatewayKey(), r.subscriber(), r.sessionId(),
                    r.requestId(), r.serviceCode(), r.event(), r.input(), r.numberFormat(), r.includeRequestId(), r.timestamp(), 120, true);
            var json = tools.jackson.databind.json.JsonMapper.builder().build();
            var reply = client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/api/emulator/exchanges"))
                    .header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(inspected))).build(),
                    HttpResponse.BodyHandlers.ofString());
            assertEquals(200, reply.statusCode()); assertEquals("no-store", reply.headers().firstValue("cache-control").orElse(""));
            var body = json.readTree(reply.body()); assertTrue(body.get("errorCode").isNull());
            assertEquals(CallbackRelayTest.GOOD, body.get("responseXml").asText());
            assertTrue(body.get("requestXml").asText().contains("<type>initial</type>"));
            assertEquals("create-owner", body.get("backendExchanges").get(0).get("stage").asText());
        } finally { callback.stop(0); }
    }
}
