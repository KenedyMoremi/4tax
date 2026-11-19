package ls.fourtax.ussd.journey;

import ls.fourtax.ussd.UssdSettings;
import ls.fourtax.ussd.api.Backend;
import ls.fourtax.ussd.api.HttpBackend;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;
import static org.junit.jupiter.api.Assertions.*;

class RegistrationPlaceholderTest {
    @Test void placeholderNeverReceivesOwnerTokensOrBusinessRecords() {
        var settings = new UssdSettings("test-gateway-key-long-enough", "test-state-secret-long-enough-12345", 160, 900,
                "https://auth.invalid", "https://auth.invalid", "https://auth.invalid/oauth2/jwks", "test", "test", "https://example.com");
        var backend = new HttpBackend(settings, JsonMapper.builder().build(), new ls.fourtax.ussd.api.ApiTrace());
        var error = assertThrows(Backend.Failure.class, () -> backend.register("private-token", null, "operation"));
        assertEquals("SERVICE_UNAVAILABLE", error.code);
    }
}
