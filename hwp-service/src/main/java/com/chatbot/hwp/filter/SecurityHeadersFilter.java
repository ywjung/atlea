package com.chatbot.hwp.filter;

import jakarta.servlet.*;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;

import java.io.IOException;

/**
 * Security headers filter to add HTTP security headers to all responses
 *
 * Protects against:
 * - Clickjacking attacks (X-Frame-Options)
 * - MIME-sniffing attacks (X-Content-Type-Options)
 * - Cross-site scripting (X-XSS-Protection, Content-Security-Policy)
 * - Information disclosure (Referrer-Policy)
 * - Feature abuse (Permissions-Policy)
 */
@Component
public class SecurityHeadersFilter implements Filter {

    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain)
            throws IOException, ServletException {

        HttpServletResponse httpResponse = (HttpServletResponse) response;

        // Prevent MIME-sniffing attacks
        httpResponse.setHeader("X-Content-Type-Options", "nosniff");

        // Prevent clickjacking by blocking iframe embedding
        httpResponse.setHeader("X-Frame-Options", "DENY");

        // Enable XSS protection in browsers
        httpResponse.setHeader("X-XSS-Protection", "1; mode=block");

        // Content Security Policy - restrict resource loading
        httpResponse.setHeader("Content-Security-Policy",
                "default-src 'self'; " +
                "script-src 'self'; " +
                "style-src 'self' 'unsafe-inline'; " +  // Allow inline styles for Swagger UI
                "img-src 'self' data:; " +  // Allow data URIs for images
                "font-src 'self'; " +
                "connect-src 'self'; " +
                "frame-ancestors 'none'");  // Prevent embedding

        // Control referrer information leakage
        httpResponse.setHeader("Referrer-Policy", "strict-origin-when-cross-origin");

        // Restrict browser features (permissions)
        httpResponse.setHeader("Permissions-Policy",
                "geolocation=(), " +
                "microphone=(), " +
                "camera=(), " +
                "payment=(), " +
                "usb=()");

        chain.doFilter(request, response);
    }
}
