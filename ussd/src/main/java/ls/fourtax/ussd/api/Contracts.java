package ls.fourtax.ussd.api;

import java.util.List;
import java.util.Map;

/** Local consumer contracts. The auth API is authoritative for authentication. */
public final class Contracts {
    private Contracts() {}
    public record PinRequest(String mobileNumber, String pin) {
        @Override public String toString() { return "PinRequest[redacted]"; }
    }
    public record TokenReply(String ownerId, String accessToken, String tokenType, long expiresIn) {
        @Override public String toString() { return "TokenReply[redacted]"; }
    }
    public record Owner(String idNumber, String fullNames) {}
    public record Source(String channel, String language) {}
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
    public record BusinessRegistration(String sector, Owner owner, Map<String, Object> details,
            List<Map<String, String>> employees, List<Map<String, String>> routes,
            List<Map<String, String>> livestock, Source source) {
        @Override public String toString() { return "BusinessRegistration[redacted]"; }
    }
    public record RegistrationReply(String entityId, String reference) {}
    public record ApiError(String code, String message, Map<String, String> fields) {}
}
