package ls.fourtax.ussd.journey;

import static ls.fourtax.ussd.journey.TestSupport.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import ls.fourtax.ussd.api.ApiTrace;
import ls.fourtax.ussd.callback.*;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import tools.jackson.databind.json.JsonMapper;

class InspectionCallbackTest {
    static final String START = "<ussdAppRequest><type>initial</type><msisdn>26658123456</msisdn><network>VOD</network>"
            + "<sessionId>inspection-test</sessionId><requestId>start</requestId></ussdAppRequest>";
    @Test void inspectionRequiresGatewayCredentialsAndLeavesTheNormalXmlContractUnchanged() throws Exception {
        var d = new Driver(new MemoryStore(), new FakeBackend()); var trace = new ApiTrace();
        var json = JsonMapper.builder().build();
        var mvc = MockMvcBuilders.standaloneSetup(new XmlCallbackController(d.coordinator, new Messages(), trace, json))
                .addFilters(new GatewayFilter(settings())).build();
        String url = "/ussd/callback/grapevine";
        assertEquals(401, mvc.perform(post(url + "/inspect").contentType("application/xml").content(START)).andReturn().getResponse().getStatus());
        var xml = mvc.perform(post(url).header("X-Gateway-Key", settings().gatewayKey()).contentType("application/xml").content(START))
                .andReturn().getResponse();
        assertEquals(200, xml.getStatus()); assertTrue(xml.getContentType().startsWith("application/xml"));
        var inspected = mvc.perform(post(url + "/inspect").header("X-Gateway-Key", settings().gatewayKey()).contentType("application/xml")
                .accept("application/json").content(START)).andReturn().getResponse();
        assertEquals(200, inspected.getStatus()); assertEquals("no-store", inspected.getHeader("Cache-Control"));
        var body = json.readTree(inspected.getContentAsString());
        assertEquals(xml.getContentAsString(), body.get("responseXml").asText()); assertTrue(body.get("exchanges").isEmpty());
        assertEquals(400, mvc.perform(post(url + "/inspect").header("X-Gateway-Key", settings().gatewayKey())
                .contentType("application/xml").content("<!DOCTYPE x><broken>" )).andReturn().getResponse().getStatus());
        try (var capture = trace.begin()) { assertTrue(capture.exchanges().isEmpty()); }
    }
}
