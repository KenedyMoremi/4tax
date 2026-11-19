package ls.fourtax.emulator;

import java.util.Map;

public final class Contracts {
    private Contracts() {}
    public enum Event { START, INPUT, ABORT, TIMEOUT }
    public enum NumberFormat { INTERNATIONAL, E164, LOCAL }
    public record GeneratorRequest(int count, String prefix, String mnc) {}
    public record Subscriber(String id, String mobileNumber, String imsi, String network, String mcc, String mnc) {}
    public record ExchangeRequest(String callbackUrl, String gatewayHeader, String gatewayKey, Subscriber subscriber,
            String sessionId, String requestId, String serviceCode, Event event, String input,
            NumberFormat numberFormat, boolean includeRequestId, String timestamp, int timeoutSeconds) {
        @Override public String toString() { return "ExchangeRequest[redacted]"; }
    }
    public record ExchangeReply(String callbackUrl, String effectiveUrl, String sessionId, String requestId,
            String event, String timestamp, String requestXml, String responseXml, int httpStatus,
            long durationMs, String prompt, String state, String responseType, Map<String, String> responseHeaders,
            String errorCode, String errorMessage) {
        @Override public String toString() { return "ExchangeReply[redacted]"; }
    }
    public record GatewayReply(String prompt, String state, String responseType) {}
    public record ApiError(String code, String message) {}
}
