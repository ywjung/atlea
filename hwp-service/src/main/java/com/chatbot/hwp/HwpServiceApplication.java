package com.chatbot.hwp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * HWP Processing Service Application
 *
 * Spring Boot application for extracting text from HWP (Hangul Word Processor) files.
 * Provides REST API endpoints for Python chatbot integration.
 */
@SpringBootApplication
public class HwpServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(HwpServiceApplication.class, args);
    }
}
