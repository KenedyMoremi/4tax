package ls.fourtax.ussd.journey;

import static ls.fourtax.ussd.journey.State.*;
import static ls.fourtax.ussd.api.Contracts.*;
import java.util.*;
import ls.fourtax.ussd.api.Backend;
import ls.fourtax.ussd.session.SessionStore;

/** Owner-only sales capture. Free text becomes a reviewed AI proposal before any ledger posting. */
public class TransactionJourney {
    private final Backend backend;
    private final NodeRouter router;
    private final SessionStore store;
    private final Crypto crypto;
    public TransactionJourney(Backend backend, NodeRouter router, SessionStore store, Crypto crypto) {
        this.backend = backend; this.router = router; this.store = store;
        this.crypto = crypto;
    }
    static List<String> fields(String sector) {
        var result = new ArrayList<>(switch (sector) {
            case "transport" -> List.of("route", "passengers", "fareCost");
            case "services" -> List.of("service", "serviceCost");
            case "ecommerce", "retail", "agriculture" -> List.of("goods", "totalValue");
            default -> throw new IllegalArgumentException("Unknown sector");
        });
        result.add("paymentDetails"); result.add("buyer"); return result;
    }
    public void begin(Session s) {
        s.draft = null; s.transaction = store.transaction(crypto.digest(s.mobile)); s.transactionResult = null;
        if (s.transaction != null && s.transaction.meaningful() && s.ownerId.equals(s.transaction.ownerId)) {
            if (s.transaction.proposal != null && s.transaction.proposal.status().equals("posted")) {
                s.transactionResult = s.transaction.proposal.reference(); s.transaction = null; router.go(s, "TX_DONE");
            } else router.go(s, "TX_RESUME");
            return;
        }
        s.transaction = null; load(s, 1);
    }
    private void load(Session s, int page) {
        try {
            var reply = backend.businesses(s.token, page);
            s.businesses = reply.businesses(); s.businessPage = page; s.nextBusinessPage = reply.nextPage();
            if (page == 1 && s.businesses.size() == 1 && s.nextBusinessPage == null) select(s, s.businesses.getFirst());
            else router.go(s, s.businesses.isEmpty() ? "TX_EMPTY" : "TX_BUSINESS");
        } catch (Backend.Failure error) { fail(s, error, "TX_LOAD"); }
    }
    public void nextBusinesses(Session s) { load(s,s.nextBusinessPage); }
    public void previousBusinesses(Session s) { load(s,s.businessPage-1); }
    private void select(Session s, BusinessSummary business) {
        if (!RegistrationSchema.sectors().contains(business.sector())) { s.error = "error.unavailable"; return; }
        s.transaction = new TransactionDraft(); s.transaction.ownerId = s.ownerId;
        s.transaction.business = business; s.transaction.language = s.language;
        router.go(s, "TX_FIELD:" + fields(business.sector()).getFirst());
        save(s);
    }
    public void input(Session s, String input) {
        if (s.node.equals("TX_LOAD")) { if (input.equals("1")) load(s, s.businessPage); else invalid(s); return; }
        if (s.node.equals("TX_EMPTY")) { if (input.equals("1")) load(s, 1); else if (input.equals("2")) router.go(s, "AUTH_MENU"); else invalid(s); return; }
        if (s.node.equals("TX_BUSINESS")) {
            try {
                int option = Integer.parseInt(input);
                if (option >= 1 && option <= s.businesses.size()) select(s, s.businesses.get(option-1));
                else invalid(s);
            } catch (NumberFormatException e) { invalid(s); }
            return;
        }
        if (s.node.equals("TX_DONE")) {
            if (input.equals("1") || input.equals("2")) {
                store.deleteTransaction(crypto.digest(s.mobile));
                if (input.equals("1")) begin(s); else router.go(s, "AUTH_MENU");
            } else invalid(s);
            return;
        }
        var draft = s.transaction;
        if (draft == null) { router.go(s, "AUTH_MENU"); return; }
        if (s.node.equals("TX_RESUME")) {
            if (input.equals("1")) {
                if (draft.frozen && (draft.proposal==null || !draft.action.equals("propose"))) submit(s);
                else if (draft.frozen) router.go(s,"TX_PREVIEW");
                else if (draft.node.equals("TX_REVIEW")) prepare(s);
                else router.go(s,draft.node);
                save(s);
            }
            else if (input.equals("2") && !draft.frozen) {
                store.deleteTransaction(crypto.digest(s.mobile)); s.transaction = null; load(s, 1);
            } else invalid(s);
            return;
        }
        var names = fields(draft.business.sector());
        if (s.node.startsWith("TX_FIELD:")) {
            if (draft.frozen) { router.go(s, draft.proposal == null ? "TX_RETRY" : "TX_PREVIEW"); return; }
            String value = input.strip().replaceAll("\\s+", " ");
            if (value.equals("-") || value.isBlank() || value.length() > 256 || value.chars().anyMatch(Character::isISOControl)) { invalid(s); return; }
            String field = s.node.substring(9);
            draft.fields.put(field, field.equals("buyer") && value.equals("@skip") ? "N/A" : value);
            if (draft.editing) { draft.editing = false; prepare(s); }
            else {
                int next = names.indexOf(field)+1;
                if (next==names.size()) prepare(s); else router.go(s,"TX_FIELD:"+names.get(next));
            }
        } else if (s.node.equals("TX_EDIT")) {
            if(input.equals("@prepare")) { prepare(s); return; }
            try {
                int choice = Integer.parseInt(input)-1;
                if (choice < 0 || choice >= names.size()) { invalid(s); return; }
                draft.editing = true; router.go(s, "TX_FIELD:" + names.get(choice));
            } catch (NumberFormatException e) { invalid(s); }
        } else if (s.node.equals("TX_PREVIEW")) {
            if(input.equals("@edit")) { draft.editAfterCancel=true; draft.action="cancel"; submit(s); }
            else if (input.equals("1") || input.equals("2")) { draft.editAfterCancel=false; draft.action = input.equals("1") ? "confirm" : "cancel"; submit(s); }
            else invalid(s);
        } else if (s.node.equals("TX_RETRY")) { if (input.equals("1")) submit(s); else invalid(s); }
        else invalid(s);
        if (!"error.invalid".equals(s.error)) save(s);
    }
    private void prepare(Session s) { s.transaction.action="propose"; submit(s); }
    private void submit(Session s) {
        var d = s.transaction; d.frozen = true;
        router.go(s, "TX_RETRY");
        save(s);
        store.saveSession(s.storageKey, s); // Persist the operation/stage before I/O, including before a process crash.
        try {
            TransactionReply reply = d.action.equals("propose")
                    ? backend.proposeTransaction(s.token, new TransactionRequest("USSD", "propose", d.business.entityId(), d.business.sector(),
                            new LinkedHashMap<>(d.fields), d.language), d.operationId)
                    : backend.resolveTransaction(s.token, new TransactionAction("USSD", d.action, d.business.entityId(), d.proposal.transactionId()), d.operationId);
            if (reply.status().equals("posted")) {
                // Retain a receipt until acknowledged: a lost MNO success reply must not invite a duplicate sale.
                d.fields.clear(); d.node = "TX_DONE";
                d.proposal = new TransactionReply(reply.transactionId(), "posted", reply.reference(), "", "");
                store.saveTransaction(crypto.digest(s.mobile), d);
                s.transactionResult = reply.reference(); s.transaction = null; router.go(s, "TX_DONE");
            } else if (reply.status().equals("cancelled")) {
                if(d.editAfterCancel) {
                    d.editAfterCancel=false; d.frozen=false; d.proposal=null; d.action="propose";
                    d.operationId=UUID.randomUUID().toString(); router.go(s,"TX_EDIT");
                } else { store.deleteTransaction(crypto.digest(s.mobile)); s.transaction=null; router.go(s,"AUTH_MENU"); s.error="tx.cancelled"; }
            }
            else if (reply.status().equals("pending") && d.action.equals("propose")) { d.proposal = reply; router.go(s, "TX_PREVIEW"); }
            else throw new Backend.Failure("SERVICE_UNAVAILABLE");
        } catch (Backend.Failure error) {
            if(error.code.equals("ALREADY_POSTED") && d.action.equals("cancel")) {
                d.editAfterCancel=false; d.action="confirm"; submit(s); return;
            }
            if (Set.of("VALIDATION_ERROR", "CLARIFICATION_REQUIRED").contains(error.code) && d.action.equals("propose")) {
                d.frozen = false; d.operationId = UUID.randomUUID().toString(); router.go(s, "TX_EDIT"); s.error = "tx.clarify";
            } else if (error.code.equals("PROPOSAL_EXPIRED_OR_CHANGED") && d.action.equals("confirm")) {
                // The API rejected confirmation. Retire that proposal before permitting a fresh one.
                d.editAfterCancel=true; d.action="cancel"; submit(s);
                if(s.node.equals("TX_EDIT")) s.error="tx.expired";
            } else fail(s, error, "TX_RETRY");
        }
    }
    private void fail(Session s, Backend.Failure error, String retry) {
        if (error.code.equals("LOGIN_REQUIRED")) {
            s.afterLogin = retry; s.clearAuthentication(); router.go(s, "LOGIN_PIN"); s.error = "error.expired";
        } else { router.go(s, retry); s.error = "error.unavailable"; }
    }
    public void back(Session s) {
        if (s.node.equals("TX_DONE")) store.deleteTransaction(crypto.digest(s.mobile));
        var d = s.transaction;
        if (d != null && d.frozen) { router.go(s, d.proposal == null || !d.action.equals("propose") ? "TX_RETRY" : "TX_PREVIEW"); s.error = "tx.finishFirst"; return; }
        if (s.node.startsWith("TX_FIELD:") && d != null) {
            if (d.editing) { d.editing = false; router.go(s, "TX_EDIT"); return; }
            var names = fields(d.business.sector()); int previous = names.indexOf(s.node.substring(9))-1;
            if (previous >= 0) { router.go(s, "TX_FIELD:" + names.get(previous)); return; }
        }
        s.transaction = null; router.go(s, "AUTH_MENU");
    }
    private void invalid(Session s) { s.error = "error.invalid"; }
    private void save(Session s) {
        if (s.transaction != null && s.transaction.meaningful()) {
            if (s.node.startsWith("TX_") && !s.node.equals("TX_RESUME")) s.transaction.node = s.node;
            store.saveTransaction(crypto.digest(s.mobile), s.transaction);
        }
    }
    static String screen(Session s, Messages m) {
        var d = s.transaction;
        if (s.node.equals("TX_RESUME")) return m.text(s.language, d.frozen ? "tx.resumeFrozen" : "tx.resume");
        if (s.node.startsWith("TX_FIELD:")) return m.text(s.language, "tx.prompt." + s.node.substring(9));
        if (s.node.equals("TX_PREVIEW")) {
            var preview = d.proposal.preview();
            String body = d.proposal.summary();
            if (preview != null) {
                body = m.text(s.language, "tx.preview."+preview.action()) + "\n" + preview.description()
                        + "\n" + m.text(s.language, "tx.preview.date") + ": " + preview.date()
                        + "\n" + m.text(s.language, "tx.preview.net") + ": M" + preview.net()
                        + "\n" + m.text(s.language, "tx.preview.tax") + ": M" + preview.tax()
                        + "\n" + m.text(s.language, "tx.preview.total") + ": M" + preview.total()
                        + "\n" + m.text(s.language, "tx.field.buyer") + ": " + preview.buyer();
                if (preview.paymentAccount() != null && !preview.paymentAccount().isBlank())
                    body += "\n" + m.text(s.language, "tx.preview.account") + ": "
                            + (Set.of("1000","1010","1020","1030").contains(preview.paymentAccount())
                                ? m.text(s.language, "tx.account."+preview.paymentAccount()) : preview.paymentAccount());
                if (preview.dueDate() != null && !preview.dueDate().isBlank()) body += "\n" + m.text(s.language, "tx.preview.dueDate") + ": " + preview.dueDate();
            }
            return m.text(s.language, "tx.preview") + "\n" + body;
        }
        if (s.node.equals("TX_DONE")) return m.text(s.language, "tx.success", s.transactionResult);
        if (s.node.equals("TX_EMPTY")) return m.text(s.language, "tx.empty");
        if (s.node.equals("TX_LOAD")) return m.text(s.language,"tx.loadFailed");
        return m.text(s.language, "tx.retry");
    }
}
