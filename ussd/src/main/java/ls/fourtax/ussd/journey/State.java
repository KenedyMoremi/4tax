package ls.fourtax.ussd.journey;

import java.util.*;
import ls.fourtax.ussd.api.Contracts.*;

public final class State {
    public static final int NAVIGATION_VERSION=5;
    private State() {}
    public static final class Session {
        public int navigationVersion;
        public String mobile;
        public String language = "en";
        public String node = "LANGUAGE";
        public int page;
        public String error;
        public String terminal;
        public String token;
        public String ownerId;
        public long tokenExpiry;
        public String pinDigest;
        public String pinNonce;
        public boolean editing;
        public boolean resumeAfterLogin;
        public boolean registered;
        public List<BusinessSummary> businesses = new ArrayList<>();
        public int businessPage = 1;
        public Integer nextBusinessPage;
        public TransactionDraft transaction;
        public String afterLogin;
        public String transactionResult;
        public String registrationResult;
        public List<String> history = new ArrayList<>();
        public Draft draft;
        @com.fasterxml.jackson.annotation.JsonIgnore
        public String storageKey;
        public Session() {}
        public Session(String mobile) { this.mobile = mobile; this.navigationVersion = NAVIGATION_VERSION; }
        public void clearAuthentication() { token = null; ownerId = null; tokenExpiry = 0; clearPin(); }
        public void clearPin() { pinDigest = null; pinNonce = null; }
    }
    public static final class TransactionDraft {
        public String operationId = UUID.randomUUID().toString();
        public String ownerId;
        public BusinessSummary business;
        public String language;
        public Map<String, String> fields = new LinkedHashMap<>();
        public boolean editing;
        public boolean frozen;
        public boolean editAfterCancel;
        public boolean summaryCapture;
        public String action = "propose";
        public String node = "TX_EDIT";
        public TransactionReply proposal;
        public boolean meaningful() { return !fields.isEmpty() || frozen || proposal != null; }
    }
    public static final class Draft {
        public int schemaVersion = 2;
        public Map<String, List<Map<String, String>>> collections = new LinkedHashMap<>();
        public String operationId = UUID.randomUUID().toString();
        public String sector;
        public String language = "en";
        public String node = "SECTOR";
        public Map<String, String> answers = new LinkedHashMap<>();
        public boolean authenticationStarted;
        public boolean collectOwnerDetails = true;
        public boolean mayHaveSubmitted;
        public String ownerId;
        public Draft() {}
        public boolean meaningful() { return (authenticationStarted && ownerId==null) || mayHaveSubmitted || !answers.isEmpty()
                || collections.values().stream().anyMatch(rows -> !rows.isEmpty()); }
    }
}
