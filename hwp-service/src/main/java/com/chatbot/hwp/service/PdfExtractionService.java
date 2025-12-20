package com.chatbot.hwp.service;

import com.chatbot.hwp.model.PdfExtractionResponse;
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
        return extractText(file, 0, 0);
    }

    /**
     * Extract text from PDF file with chunking
     */
    public PdfExtractionResponse extractText(MultipartFile file, int chunkSize, int chunkOverlap) {
        long startTime = System.currentTimeMillis();
        String filename = file.getOriginalFilename();

        try {
            log.info("Extracting text from PDF: {}", filename);
            byte[] fileBytes = file.getBytes();

            return extractTextFromBytes(fileBytes, filename, chunkSize, chunkOverlap, startTime);
        } catch (IOException e) {
            log.error("Failed to read file bytes: {}", e.getMessage());
            return buildErrorResponse(filename, "Failed to read file", startTime);
        }
    }

    /**
     * Extract text from base64-encoded PDF
     */
    public PdfExtractionResponse extractTextFromBase64(String base64Content, String filename) {
        return extractTextFromBase64(base64Content, filename, 0, 0);
    }

    /**
     * Extract text from base64-encoded PDF with chunking
     */
    public PdfExtractionResponse extractTextFromBase64(String base64Content, String filename,
                                                       int chunkSize, int chunkOverlap) {
        long startTime = System.currentTimeMillis();

        try {
            log.info("Extracting text from base64 PDF: {}", filename);
            byte[] fileBytes = Base64.getDecoder().decode(base64Content);

            return extractTextFromBytes(fileBytes, filename, chunkSize, chunkOverlap, startTime);
        } catch (IllegalArgumentException e) {
            log.error("Invalid base64 encoding: {}", e.getMessage());
            return buildErrorResponse(filename, "Invalid base64 encoding", startTime);
        }
    }

    /**
     * Core extraction logic from byte array
     */
    private PdfExtractionResponse extractTextFromBytes(byte[] fileBytes, String filename,
                                                       int chunkSize, int chunkOverlap,
                                                       long startTime) {
        try (PDDocument document = Loader.loadPDF(fileBytes)) {
            PDFTextStripper stripper = new PDFTextStripper();
            stripper.setSortByPosition(true);

            StringBuilder fullText = new StringBuilder();
            int pageCount = document.getNumberOfPages();

            // Extract text from all pages
            for (int i = 1; i <= pageCount; i++) {
                stripper.setStartPage(i);
                stripper.setEndPage(i);
                String pageText = stripper.getText(document);
                if (pageText != null && !pageText.trim().isEmpty()) {
                    fullText.append(pageText);
                    if (i < pageCount) {
                        fullText.append("\n\n");
                    }
                }
            }

            String extractedText = fullText.toString();
            long processingTime = System.currentTimeMillis() - startTime;

            log.info("Successfully extracted {} characters from {} pages in {}ms",
                    extractedText.length(), pageCount, processingTime);

            // Build response with or without chunks
            if (chunkSize > 0) {
                List<PdfExtractionResponse.TextChunk> chunks = createChunks(
                        extractedText, filename, chunkSize, chunkOverlap);

                return PdfExtractionResponse.builder()
                        .text(extractedText)
                        .chunks(chunks)
                        .pageCount(pageCount)
                        .success(true)
                        .filename(filename)
                        .processingTimeMs(processingTime)
                        .build();
            } else {
                return PdfExtractionResponse.builder()
                        .text(extractedText)
                        .pageCount(pageCount)
                        .success(true)
                        .filename(filename)
                        .processingTimeMs(processingTime)
                        .build();
            }
        } catch (IOException e) {
            log.error("Failed to extract text from PDF: {}", e.getMessage());
            return buildErrorResponse(filename, "PDF extraction failed", startTime);
        }
    }

    /**
     * Create text chunks using recursive character splitting
     */
    private List<PdfExtractionResponse.TextChunk> createChunks(String text, String filename,
                                                               int chunkSize, int chunkOverlap) {
        List<PdfExtractionResponse.TextChunk> chunks = new ArrayList<>();

        if (text == null || text.isEmpty()) {
            return chunks;
        }

        // Separators in order of preference (similar to RecursiveCharacterTextSplitter)
        String[] separators = {"\n\n", "\n", ". ", " ", ""};

        List<String> splitTexts = recursiveSplit(text, separators, chunkSize, chunkOverlap);

        for (int i = 0; i < splitTexts.size(); i++) {
            chunks.add(PdfExtractionResponse.TextChunk.builder()
                    .text(splitTexts.get(i))
                    .chunkIndex(i)
                    .totalChunks(splitTexts.size())
                    .filename(filename)
                    .pageNumbers(new ArrayList<>()) // Page tracking can be added if needed
                    .build());
        }

        log.debug("Created {} chunks from text", chunks.size());
        return chunks;
    }

    /**
     * Recursive text splitting algorithm
     */
    private List<String> recursiveSplit(String text, String[] separators, int chunkSize, int chunkOverlap) {
        List<String> result = new ArrayList<>();

        if (text.length() <= chunkSize) {
            result.add(text);
            return result;
        }

        // Try each separator
        for (String separator : separators) {
            if (separator.isEmpty() || !text.contains(separator)) {
                continue;
            }

            String[] splits = text.split(separator, -1);
            List<String> currentChunk = new ArrayList<>();
            int currentLength = 0;

            for (String split : splits) {
                int splitLength = split.length();

                if (currentLength + splitLength + separator.length() > chunkSize && !currentChunk.isEmpty()) {
                    // Save current chunk
                    String chunk = String.join(separator, currentChunk);
                    result.add(chunk);

                    // Start new chunk with overlap
                    if (chunkOverlap > 0 && !currentChunk.isEmpty()) {
                        currentChunk = new ArrayList<>(currentChunk.subList(
                                Math.max(0, currentChunk.size() - 1), currentChunk.size()));
                        currentLength = currentChunk.stream()
                                .mapToInt(String::length)
                                .sum() + separator.length() * (currentChunk.size() - 1);
                    } else {
                        currentChunk = new ArrayList<>();
                        currentLength = 0;
                    }
                }

                currentChunk.add(split);
                currentLength += splitLength + separator.length();
            }

            // Add remaining chunk
            if (!currentChunk.isEmpty()) {
                result.add(String.join(separator, currentChunk));
            }

            return result;
        }

        // Fallback: split by character count if no separator worked
        for (int i = 0; i < text.length(); i += chunkSize - chunkOverlap) {
            int end = Math.min(i + chunkSize, text.length());
            result.add(text.substring(i, end));
        }

        return result;
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
