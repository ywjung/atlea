package com.chatbot.document;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * HWP Processing Service Application
 *
 * Spring Boot application for extracting text from HWP (Hangul Word Processor) files.
 * Provides REST API endpoints for Python chatbot integration.
 */
@SpringBootApplication
public class DocumentServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocumentServiceApplication.class, args);
    }
}
