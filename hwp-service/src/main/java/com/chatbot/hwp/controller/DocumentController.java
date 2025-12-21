package com.chatbot.hwp.controller;

import com.chatbot.hwp.model.DocumentExtractionRequest;
import com.chatbot.hwp.model.DocumentExtractionResponse;
import com.chatbot.hwp.model.ErrorResponse;
import com.chatbot.hwp.service.*;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDateTime;
import java.util.Base64;

@Slf4j
@RestController
@RequestMapping("/api/document")
@RequiredArgsConstructor
@Tag(name = "Document Text Extraction", description = "Unified API for extracting text from all supported document formats")
public class DocumentController {

    private final PdfExtractionService pdfExtractionService;
    private final HwpExtractionService hwpExtractionService;
    private final HwpxExtractionService hwpxExtractionService;
    private final OfficeExtractionService officeExtractionService;

    @Operation(
            summary = "Health check",
            description = "Check if the Document service is running and healthy"
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Service is running",
                    content = @Content(schema = @Schema(implementation = String.class)))
    })
    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("Document Service is running");
    }

    @Operation(
            summary = "Extract text from any supported document",
            description = "Upload a document file and extract its text content. Supports PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX files up to 50MB."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Text extracted successfully",
                    content = @Content(schema = @Schema(implementation = DocumentExtractionResponse.class))),
            @ApiResponse(responseCode = "400", description = "Invalid file format or size",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))),
            @ApiResponse(responseCode = "500", description = "Extraction failed",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    })
    @PostMapping(value = "/extract", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<?> extractText(
            @Parameter(description = "Document file to extract text from (*.pdf, *.hwp, *.hwpx, *.doc, *.docx, *.xls, *.xlsx, *.ppt, *.pptx, max 50MB)", required = true)
            @RequestParam("file") MultipartFile file) {

        log.info("Received document extraction request: {}", file.getOriginalFilename());

        // Detect file type and route to appropriate service
        String filename = file.getOriginalFilename();
        if (filename == null || filename.isEmpty()) {
            return ResponseEntity
                    .badRequest()
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.BAD_REQUEST.value())
                            .error("Invalid filename")
                            .message("Filename is required")
                            .path("/api/document/extract")
                            .build());
        }

        String lowerFilename = filename.toLowerCase();
        DocumentExtractionResponse response;

        try {
            if (lowerFilename.endsWith(".pdf")) {
                if (!pdfExtractionService.isValidPdfFile(file)) {
                    return buildBadRequestResponse("Invalid PDF file");
                }
                response = convertPdfResponse(pdfExtractionService.extractText(file));

            } else if (lowerFilename.endsWith(".hwp")) {
                if (!hwpExtractionService.isValidHwpFile(file)) {
                    return buildBadRequestResponse("Invalid HWP file");
                }
                response = convertHwpResponse(hwpExtractionService.extractText(file));

            } else if (lowerFilename.endsWith(".hwpx")) {
                if (!hwpxExtractionService.isValidHwpxFile(file)) {
                    return buildBadRequestResponse("Invalid HWPX file");
                }
                response = hwpxExtractionService.extractText(file);

            } else if (lowerFilename.endsWith(".doc") || lowerFilename.endsWith(".docx") ||
                       lowerFilename.endsWith(".xls") || lowerFilename.endsWith(".xlsx") ||
                       lowerFilename.endsWith(".ppt") || lowerFilename.endsWith(".pptx")) {
                if (!officeExtractionService.isValidOfficeFile(file)) {
                    return buildBadRequestResponse("Invalid Office file");
                }
                response = officeExtractionService.extractText(file);

            } else {
                return ResponseEntity
                        .badRequest()
                        .body(ErrorResponse.builder()
                                .timestamp(LocalDateTime.now())
                                .status(HttpStatus.BAD_REQUEST.value())
                                .error("Unsupported file format")
                                .message("Supported formats: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX")
                                .path("/api/document/extract")
                                .build());
            }

            if (!response.isSuccess()) {
                return ResponseEntity
                        .status(HttpStatus.INTERNAL_SERVER_ERROR)
                        .body(ErrorResponse.builder()
                                .timestamp(LocalDateTime.now())
                                .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                                .error("Extraction failed")
                                .message("Failed to process document file")
                                .path("/api/document/extract")
                                .build());
            }

            return ResponseEntity.ok(response);

        } catch (Exception e) {
            log.error("Unexpected error during document extraction: {}", e.getMessage(), e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                            .error("Internal Server Error")
                            .message("An unexpected error occurred while processing your request")
                            .path("/api/document/extract")
                            .build());
        }
    }

    @Operation(
            summary = "Extract text from base64-encoded document",
            description = "Send document content as base64-encoded string and extract text. Useful for API integrations where file upload is not available."
    )
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Text extracted successfully",
                    content = @Content(schema = @Schema(implementation = DocumentExtractionResponse.class))),
            @ApiResponse(responseCode = "400", description = "Invalid request or missing fileContent",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class))),
            @ApiResponse(responseCode = "500", description = "Extraction failed",
                    content = @Content(schema = @Schema(implementation = ErrorResponse.class)))
    })
    @PostMapping(value = "/extract/base64", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> extractTextFromBase64(
            @Parameter(description = "Extraction request with base64-encoded document content", required = true)
            @Valid @RequestBody DocumentExtractionRequest request) {

        log.info("Received base64 document extraction request: {}", request.getFilename());

        // Security: Validate base64 content size before processing
        if (request.getFileContent().length() > 70000000) {
            return ResponseEntity
                    .badRequest()
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.BAD_REQUEST.value())
                            .error("Payload too large")
                            .message("Base64 content exceeds maximum size of 50MB")
                            .path("/api/document/extract/base64")
                            .build());
        }

        // Security: Validate decoded size
        byte[] fileBytes;
        try {
            fileBytes = Base64.getDecoder().decode(request.getFileContent());

            if (fileBytes.length > 50 * 1024 * 1024) {
                return ResponseEntity
                        .badRequest()
                        .body(ErrorResponse.builder()
                                .timestamp(LocalDateTime.now())
                                .status(HttpStatus.BAD_REQUEST.value())
                                .error("File too large")
                                .message("Decoded file size exceeds 50MB limit")
                                .path("/api/document/extract/base64")
                                .build());
            }
        } catch (IllegalArgumentException e) {
            log.error("Invalid base64 encoding: {}", e.getMessage());
            return ResponseEntity
                    .badRequest()
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.BAD_REQUEST.value())
                            .error("Invalid base64")
                            .message("Invalid base64 encoding")
                            .path("/api/document/extract/base64")
                            .build());
        }

        String filename = request.getFilename();
        String lowerFilename = filename.toLowerCase();
        DocumentExtractionResponse response;

        try {
            if (lowerFilename.endsWith(".pdf")) {
                response = convertPdfResponse(
                        pdfExtractionService.extractTextFromBase64(request.getFileContent(), filename));

            } else if (lowerFilename.endsWith(".hwp")) {
                response = convertHwpResponse(
                        hwpExtractionService.extractTextFromBase64(request.getFileContent(), filename));

            } else if (lowerFilename.endsWith(".hwpx")) {
                response = hwpxExtractionService.extractTextFromBase64(request.getFileContent(), filename);

            } else if (lowerFilename.endsWith(".doc") || lowerFilename.endsWith(".docx") ||
                       lowerFilename.endsWith(".xls") || lowerFilename.endsWith(".xlsx") ||
                       lowerFilename.endsWith(".ppt") || lowerFilename.endsWith(".pptx")) {
                response = officeExtractionService.extractTextFromBase64(request.getFileContent(), filename);

            } else {
                return ResponseEntity
                        .badRequest()
                        .body(ErrorResponse.builder()
                                .timestamp(LocalDateTime.now())
                                .status(HttpStatus.BAD_REQUEST.value())
                                .error("Unsupported file format")
                                .message("Supported formats: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX")
                                .path("/api/document/extract/base64")
                                .build());
            }

            if (!response.isSuccess()) {
                return ResponseEntity
                        .status(HttpStatus.INTERNAL_SERVER_ERROR)
                        .body(ErrorResponse.builder()
                                .timestamp(LocalDateTime.now())
                                .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                                .error("Extraction failed")
                                .message("Failed to process document file")
                                .path("/api/document/extract/base64")
                                .build());
            }

            return ResponseEntity.ok(response);

        } catch (Exception e) {
            log.error("Unexpected error: {}", e.getMessage(), e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(ErrorResponse.builder()
                            .timestamp(LocalDateTime.now())
                            .status(HttpStatus.INTERNAL_SERVER_ERROR.value())
                            .error("Internal Server Error")
                            .message("An unexpected error occurred while processing your request")
                            .path("/api/document/extract/base64")
                            .build());
        }
    }

    /**
     * Convert PdfExtractionResponse to DocumentExtractionResponse
     */
    private DocumentExtractionResponse convertPdfResponse(com.chatbot.hwp.model.PdfExtractionResponse pdfResponse) {
        return DocumentExtractionResponse.builder()
                .text(pdfResponse.getText())
                .success(pdfResponse.isSuccess())
                .error(pdfResponse.getError())
                .filename(pdfResponse.getFilename())
                .fileType("PDF")
                .processingTimeMs(pdfResponse.getProcessingTimeMs())
                .build();
    }

    /**
     * Convert HwpExtractionResponse to DocumentExtractionResponse
     */
    private DocumentExtractionResponse convertHwpResponse(com.chatbot.hwp.model.HwpExtractionResponse hwpResponse) {
        return DocumentExtractionResponse.builder()
                .text(hwpResponse.getText())
                .success(hwpResponse.isSuccess())
                .error(hwpResponse.getError())
                .filename(hwpResponse.getFilename())
                .fileType("HWP")
                .processingTimeMs(hwpResponse.getProcessingTimeMs())
                .build();
    }

    /**
     * Build bad request response
     */
    private ResponseEntity<?> buildBadRequestResponse(String message) {
        return ResponseEntity
                .badRequest()
                .body(ErrorResponse.builder()
                        .timestamp(LocalDateTime.now())
                        .status(HttpStatus.BAD_REQUEST.value())
                        .error(message)
                        .message("File must be valid and less than 50MB")
                        .path("/api/document/extract")
                        .build());
    }

    /**
     * Security: Sanitized error handler
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
                        .message("An unexpected error occurred while processing your request")
                        .path("/api/document")
                        .build());
    }
}
