package com.chatbot.document.service;

import com.chatbot.document.model.PdfExtractionResponse;
import lombok.extern.slf4j.Slf4j;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.*;

@Slf4j
@Service
public class PdfExtractionService {

    private static final long MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
    private static final List<String> ALLOWED_EXTENSIONS = List.of(".pdf");

    /**
     * Validate if the file is a valid PDF
     */
    public boolean isValidPdfFile(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            log.warn("File is null or empty");
            return false;
        }

        // Check file size
        if (file.getSize() > MAX_FILE_SIZE) {
            log.warn("File size exceeds limit: {} bytes", file.getSize());
            return false;
        }

        // Check file extension
        String originalFilename = file.getOriginalFilename();
        if (originalFilename == null) {
            log.warn("Filename is null");
            return false;
        }

        boolean hasValidExtension = ALLOWED_EXTENSIONS.stream()
                .anyMatch(ext -> originalFilename.toLowerCase().endsWith(ext));

        if (!hasValidExtension) {
            log.warn("Invalid file extension: {}", originalFilename);
            return false;
        }

        // Check content type
        String contentType = file.getContentType();
        if (contentType != null && !contentType.equals("application/pdf")) {
            log.warn("Invalid content type: {}", contentType);
            return false;
        }

        return true;
    }

    /**
     * Extract text from PDF file (multipart upload)
     */
    public PdfExtractionResponse extractText(MultipartFile file) {
        long startTime = System.currentTimeMillis();
        String filename = file.getOriginalFilename();

        try {
            log.debug("Extracting text from PDF: {}", filename);
            byte[] fileBytes = file.getBytes();

            return extractTextFromBytes(fileBytes, filename, startTime);
        } catch (IOException e) {
            log.error("Failed to read file bytes: {}", e.getMessage());
            return buildErrorResponse(filename, "Failed to read file", startTime);
        }
    }

    /**
     * Extract text from base64-encoded PDF
     */
    public PdfExtractionResponse extractTextFromBase64(String base64Content, String filename) {
        long startTime = System.currentTimeMillis();

        try {
            log.debug("Extracting text from base64 PDF: {}", filename);
            byte[] fileBytes = Base64.getDecoder().decode(base64Content);

            return extractTextFromBytes(fileBytes, filename, startTime);
        } catch (IllegalArgumentException e) {
            log.error("Invalid base64 encoding: {}", e.getMessage());
            return buildErrorResponse(filename, "Invalid base64 encoding", startTime);
        }
    }

    /**
     * Core extraction logic from byte array
     * Optimized: Extract all pages at once instead of page-by-page
     */
    private PdfExtractionResponse extractTextFromBytes(byte[] fileBytes, String filename,
                                                       long startTime) {
        try (PDDocument document = Loader.loadPDF(fileBytes)) {
            PDFTextStripper stripper = new PDFTextStripper();
            stripper.setSortByPosition(true);

            int pageCount = document.getNumberOfPages();

            // Optimized: Extract all pages at once (much faster than page-by-page)
            String extractedText = stripper.getText(document);

            long processingTime = System.currentTimeMillis() - startTime;

            log.debug("Successfully extracted {} characters from {} pages in {}ms",
                    extractedText.length(), pageCount, processingTime);

            return PdfExtractionResponse.builder()
                    .text(extractedText)
                    .pageCount(pageCount)
                    .success(true)
                    .filename(filename)
                    .processingTimeMs(processingTime)
                    .build();
        } catch (IOException e) {
            log.error("Failed to extract text from PDF: {}", e.getMessage());
            return buildErrorResponse(filename, "PDF extraction failed", startTime);
        }
    }

    /**
     * Build error response
     */
    private PdfExtractionResponse buildErrorResponse(String filename, String errorMessage, long startTime) {
        return PdfExtractionResponse.builder()
                .text("")
                .pageCount(0)
                .success(false)
                .error(errorMessage)
                .filename(filename)
                .processingTimeMs(System.currentTimeMillis() - startTime)
                .build();
    }
}
