package ls.fourtax.ussd.api;

import java.util.List;
import java.util.Map;

/** Local consumer contracts. The auth API is authoritative for authentication. */
public final class Contracts {
    private Contracts() {}
    public enum Sector { TRANSPORT, WELLNESS, VENDOR }
    public record PinRequest(String mobileNumber, String pin) {
        @Override public String toString() { return "PinRequest[redacted]"; }
    }
    public record TokenReply(String ownerId, String accessToken, String tokenType, long expiresIn) {
        @Override public String toString() { return "TokenReply[redacted]"; }
    }
    public record Owner(String idNumber, String fullNames, String residence) {}
    public record Vehicle(String vin, String numberPlate) {}
    public record Schedule(List<String> days, String opensAt, String closesAt) {}
    public record Source(String channel, String language) {}
    public record BusinessRegistration(Sector sector, Owner owner, String businessName, String mobileNumber,
            String location, Vehicle vehicle, Schedule operatingSchedule, Source source) {
        @Override public String toString() { return "BusinessRegistration[redacted]"; }
    }
    public record RegistrationReply(String entityId, String reference) {}
    public record ApiError(String code, String message, Map<String, String> fields) {}
}
