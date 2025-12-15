package com.chatbot.hwp.service;

import com.chatbot.hwp.model.HwpExtractionResponse;
import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.paragraph.text.ParaText;
import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwplib.tool.paragraphadder.ParagraphCopier;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.io.FileUtils;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;

/**
 * Service for extracting text from HWP files
 */
@Slf4j
@Service
public class HwpExtractionService {

    /**
     * Extract text from HWP file (MultipartFile)
     *
     * @param file HWP file
     * @return Extraction response with text content
     */
    public HwpExtractionResponse extractText(MultipartFile file) {
        long startTime = System.currentTimeMillis();
        String filename = file.getOriginalFilename();

        try {
            log.info("Starting HWP extraction for file: {}", filename);

            // Create temporary file
            Path tempFile = Files.createTempFile("hwp_", ".hwp");
            file.transferTo(tempFile.toFile());

            // Extract text
            String extractedText = extractTextFromFile(tempFile.toFile());

            // Clean up
            Files.deleteIfExists(tempFile);

            int paragraphCount = extractedText.split("\n").length;
            long processingTime = System.currentTimeMillis() - startTime;

            log.info("Successfully extracted text from {}: {} paragraphs in {}ms",
                    filename, paragraphCount, processingTime);

            return HwpExtractionResponse.builder()
                    .text(extractedText)
                    .paragraphCount(paragraphCount)
                    .success(true)
                    .filename(filename)
                    .processingTimeMs(processingTime)
                    .build();

        } catch (Exception e) {
            long processingTime = System.currentTimeMillis() - startTime;
            log.error("Failed to extract text from {}: {}", filename, e.getMessage(), e);

            return HwpExtractionResponse.builder()
                    .success(false)
                    .error(e.getMessage())
                    .filename(filename)
                    .processingTimeMs(processingTime)
                    .build();
        }
    }

    /**
     * Extract text from HWP file (Base64 encoded)
     *
     * @param base64Content Base64 encoded HWP file content
     * @param filename      Original filename
     * @return Extraction response with text content
     */
    public HwpExtractionResponse extractTextFromBase64(String base64Content, String filename) {
        long startTime = System.currentTimeMillis();

        try {
            log.info("Starting HWP extraction from base64 for file: {}", filename);

            // Decode base64
            byte[] fileBytes = Base64.getDecoder().decode(base64Content);

            // Create temporary file
            Path tempFile = Files.createTempFile("hwp_", ".hwp");
            Files.write(tempFile, fileBytes);

            // Extract text
            String extractedText = extractTextFromFile(tempFile.toFile());

            // Clean up
            Files.deleteIfExists(tempFile);

            int paragraphCount = extractedText.split("\n").length;
            long processingTime = System.currentTimeMillis() - startTime;

            log.info("Successfully extracted text from {}: {} paragraphs in {}ms",
                    filename, paragraphCount, processingTime);

            return HwpExtractionResponse.builder()
                    .text(extractedText)
                    .paragraphCount(paragraphCount)
                    .success(true)
                    .filename(filename)
                    .processingTimeMs(processingTime)
                    .build();

        } catch (Exception e) {
            long processingTime = System.currentTimeMillis() - startTime;
            log.error("Failed to extract text from {}: {}", filename, e.getMessage(), e);

            return HwpExtractionResponse.builder()
                    .success(false)
                    .error(e.getMessage())
                    .filename(filename)
                    .processingTimeMs(processingTime)
                    .build();
        }
    }

    /**
     * Extract text from HWP file using hwplib
     *
     * @param file HWP file
     * @return Extracted text content
     * @throws Exception if extraction fails
     */
    private String extractTextFromFile(File file) throws Exception {
        // Read HWP file
        HWPFile hwpFile = HWPReader.fromFile(file.getAbsolutePath());

        if (hwpFile == null) {
            throw new IOException("Failed to read HWP file");
        }

        StringBuilder textBuilder = new StringBuilder();

        // Extract text from all sections
        for (Section section : hwpFile.getBodyText().getSectionList()) {
            for (Paragraph paragraph : section.getParagraphs()) {
                String paragraphText = extractParagraphText(paragraph);
                if (paragraphText != null && !paragraphText.trim().isEmpty()) {
                    textBuilder.append(paragraphText).append("\n");
                }
            }
        }

        String extractedText = textBuilder.toString().trim();

        if (extractedText.isEmpty()) {
            throw new IOException("No text content found in HWP file");
        }

        return extractedText;
    }

    /**
     * Extract text from a single paragraph
     *
     * @param paragraph HWP paragraph object
     * @return Extracted text
     */
    private String extractParagraphText(Paragraph paragraph) {
        if (paragraph == null || paragraph.getText() == null) {
            return "";
        }

        ParaText paraText = paragraph.getText();
        if (paraText == null) {
            return "";
        }

        // Get normal text
        String normalText = paraText.toString();
        if (normalText != null) {
            return normalText.trim();
        }

        return "";
    }

    /**
     * Validate HWP file format
     *
     * @param file File to validate
     * @return true if valid HWP file
     */
    public boolean isValidHwpFile(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            return false;
        }

        String filename = file.getOriginalFilename();
        if (filename == null || !filename.toLowerCase().endsWith(".hwp")) {
            return false;
        }

        // Check file size (max 50MB)
        long maxSize = 50 * 1024 * 1024;
        if (file.getSize() > maxSize) {
            log.warn("File too large: {} bytes (max: {} bytes)", file.getSize(), maxSize);
            return false;
        }

        return true;
    }
}
