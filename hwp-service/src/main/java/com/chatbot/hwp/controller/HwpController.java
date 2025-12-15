package com.chatbot.hwp.controller;

import com.chatbot.hwp.model.ErrorResponse;
import com.chatbot.hwp.model.HwpExtractionRequest;
import com.chatbot.hwp.model.HwpExtractionResponse;
import com.chatbot.hwp.service.HwpExtractionService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDateTime;

/**
 * REST API Controller for HWP text extraction
 */
@Slf4j
@RestController
@RequestMapping("/api/hwp")
@RequiredArgsConstructor
public class HwpController {

    private final HwpExtractionService hwpExtractionService;

    /**
     * Health check endpoint
     *
     * @return OK status
     */
    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("HWP Service is running");
    }

    /**
     * Extract text from HWP file (multipart upload)
     *
     * @param file HWP file
     * @return Extraction response
     */
    @PostMapping(value = "/extract", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> extractText(@RequestParam("file") MultipartFile file) {
        log.info("Received HWP extraction request: {}", file.getOriginalFilename());

        // Validate file
        if (!hwpExtractionService.isValidHwpFile(file)) {
            return ResponseEntity
                    .badRequest()
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.BAD_REQUEST.value())
                            .error("Invalid HWP file")
                            .message("File must be a valid HWP file (*.hwp) and less than 50MB")
                            .path("/api/hwp/extract")
                            .build());
        }

        // Extract text
        HwpExtractionResponse response = hwpExtractionService.extractText(file);

        if (!response.isSuccess()) {
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                            .error("Extraction failed")
                            .message(response.getError())
                            .path("/api/hwp/extract")
                            .build());
        }

        return ResponseEntity.ok(response);
    }

    /**
     * Extract text from HWP file (base64 encoded)
     *
     * @param request Extraction request with base64 content
     * @return Extraction response
     */
    @PostMapping(value = "/extract/base64", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> extractTextFromBase64(@RequestBody HwpExtractionRequest request) {
        log.info("Received base64 HWP extraction request: {}", request.getFilename());

        if (request.getFileContent() == null || request.getFileContent().isEmpty()) {
            return ResponseEntity
                    .badRequest()
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.BAD_REQUEST.value())
                            .error("Invalid request")
                            .message("fileContent is required")
                            .path("/api/hwp/extract/base64")
                            .build());
        }

        // Extract text
        HwpExtractionResponse response = hwpExtractionService.extractTextFromBase64(
                request.getFileContent(),
                request.getFilename() != null ? request.getFilename() : "unknown.hwp"
        );

        if (!response.isSuccess()) {
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                            .error("Extraction failed")
                            .message(response.getError())
                            .path("/api/hwp/extract/base64")
                            .build());
        }

        return ResponseEntity.ok(response);
    }

    /**
     * Exception handler for all exceptions
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleException(Exception e) {
        log.error("Unexpected error: {}", e.getMessage(), e);

        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ErrorResponse.builder()
                        .timestamp(LocalDateTime.now())
                        .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                        .error("Internal Server Error")
                        .message(e.getMessage())
                        .path("/api/hwp")
                        .build());
    }
}
