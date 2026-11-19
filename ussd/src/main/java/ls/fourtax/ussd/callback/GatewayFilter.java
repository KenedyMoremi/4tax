package ls.fourtax.ussd.callback;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import ls.fourtax.ussd.UssdSettings;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class GatewayFilter extends OncePerRequestFilter {
    private final byte[] key;
    public GatewayFilter(UssdSettings settings) { key = settings.gatewayKey().getBytes(StandardCharsets.UTF_8); }
    @Override protected boolean shouldNotFilter(HttpServletRequest request) { return !request.getRequestURI().startsWith("/ussd/callback/"); }
    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain) throws ServletException, IOException {
        String supplied = request.getHeader("X-Gateway-Key");
        response.setHeader("Cache-Control", "no-store");
        if (supplied == null || !MessageDigest.isEqual(key, supplied.getBytes(StandardCharsets.UTF_8))) { response.setStatus(401); return; }
        chain.doFilter(request, response);
    }
}
