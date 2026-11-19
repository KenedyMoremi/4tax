package ls.fourtax.ussd.api;

import static ls.fourtax.ussd.api.Contracts.*;

public interface Backend {
    boolean ownerExists(String mobile);
    BusinessPage businesses(String ownerToken, int page);
    TransactionReply proposeTransaction(String ownerToken, TransactionRequest request, String operationId);
    TransactionReply resolveTransaction(String ownerToken, TransactionAction request, String operationId);
    TokenReply createOwner(String mobile, String pin, String operationId);
    TokenReply login(String mobile, String pin);
    RegistrationReply register(String ownerToken, BusinessRegistration request, String operationId);
    String verifyOwner(String token);

    final class Failure extends RuntimeException {
        public final String code;
        public Failure(String code) { super(code); this.code = code; }
    }
}
