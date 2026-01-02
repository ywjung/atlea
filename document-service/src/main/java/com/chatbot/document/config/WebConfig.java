package com.chatbot.document.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Web configuration for CORS and other web settings
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        // Security: Restrict CORS to specific origins (prevents CSRF and unauthorized access)
        registry.addMapping("/api/**")
                .allowedOrigins(
                    "http://localhost:8000",      // Python FastAPI backend
                    "http://localhost:3000",      // Development frontend
                    "http://127.0.0.1:8000",
                    "http://127.0.0.1:3000"
                    // Add production domains here: "https://yourdomain.com"
                )
                .allowedMethods("GET", "POST", "OPTIONS")  // Remove PUT, DELETE
                .allowedHeaders("Content-Type", "Authorization")  // Specific headers only
                .allowCredentials(true)  // Enable credentials
                .maxAge(3600);
    }
}
