package com.chatbot.document.service;

import com.chatbot.document.model.HwpExtractionResponse;
import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.paragraph.text.ParaText;
import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwplib.tool.paragraphadder.ParagraphCopier;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractMethod;
import kr.dogfoot.hwplib.tool.textextractor.TextExtractor;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.io.FileUtils;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Base64;
import java.util.Set;

/**
 * Service for extracting text from HWP files
 */
@Slf4j
@Service
public class HwpExtractionService {

    /**
     * Extract text from HWP file (MultipartFile)
     *
     * Security: Uses try-finally for guaranteed temp file cleanup, restricts file permissions
     *
     * @param file HWP file
     * @return Extraction response with text content
     */
    public HwpExtractionResponse extractText(MultipartFile file) {
        long startTime = System.currentTimeMillis();
        String filename = file.getOriginalFilename();
        Path tempFile = null;

        try {
            log.debug("Starting HWP extraction for file: {}", filename);

            // Security: Create temp file with unique name
            tempFile = Files.createTempFile("hwp_", ".hwp");

            // Security: Set restrictive permissions (owner read/write only)
            try {
                Set<PosixFilePermission> permissions = PosixFilePermissions.fromString("rw-------");
                Files.setPosixFilePermissions(tempFile, permissions);
            } catch (UnsupportedOperationException e) {
                // Windows doesn't support POSIX permissions, skip
                log.debug("POSIX permissions not supported on this system");
            }

            // Transfer file atomically
            file.transferTo(tempFile.toFile());

            // Extract text
            String extractedText = extractTextFromFile(tempFile.toFile());

            int paragraphCount = extractedText.split("\n").length;
            long processingTime = System.currentTimeMillis() - startTime;

            log.debug("Successfully extracted text from {}: {} paragraphs in {}ms",
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
                    .error("Extraction failed")  // Security: Don't expose internal details
                    .filename(filename)
                    .processingTimeMs(processingTime)
                    .build();

        } finally {
            // Security: Ensure cleanup happens even on exception
            if (tempFile != null) {
                try {
                    Files.deleteIfExists(tempFile);
                } catch (IOException e) {
                    log.error("Failed to delete temp file: {}", tempFile, e);
                }
            }
        }
    }

    /**
     * Extract text from HWP file (Base64 encoded)
     *
     * Security: Uses try-finally for guaranteed temp file cleanup, restricts file permissions
     *
     * @param base64Content Base64 encoded HWP file content
     * @param filename      Original filename
     * @return Extraction response with text content
     */
    public HwpExtractionResponse extractTextFromBase64(String base64Content, String filename) {
        long startTime = System.currentTimeMillis();
        Path tempFile = null;

        try {
            log.debug("Starting HWP extraction from base64 for file: {}", filename);

            // Decode base64
            byte[] fileBytes = Base64.getDecoder().decode(base64Content);

            // Security: Create temp file with unique name
            tempFile = Files.createTempFile("hwp_", ".hwp");

            // Security: Set restrictive permissions (owner read/write only)
            try {
                Set<PosixFilePermission> permissions = PosixFilePermissions.fromString("rw-------");
                Files.setPosixFilePermissions(tempFile, permissions);
            } catch (UnsupportedOperationException e) {
                // Windows doesn't support POSIX permissions, skip
                log.debug("POSIX permissions not supported on this system");
            }

            // Write decoded bytes to temp file
            Files.write(tempFile, fileBytes);

            // Extract text
            String extractedText = extractTextFromFile(tempFile.toFile());

            int paragraphCount = extractedText.split("\n").length;
            long processingTime = System.currentTimeMillis() - startTime;

            log.debug("Successfully extracted text from {}: {} paragraphs in {}ms",
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
                    .error("Extraction failed")  // Security: Don't expose internal details
                    .filename(filename)
                    .processingTimeMs(processingTime)
                    .build();

        } finally {
            // Security: Ensure cleanup happens even on exception
            if (tempFile != null) {
                try {
                    Files.deleteIfExists(tempFile);
                } catch (IOException e) {
                    log.error("Failed to delete temp file: {}", tempFile, e);
                }
            }
        }
    }

    /**
     * Extract text from HWP file using hwplib TextExtractor
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

        // Use TextExtractor utility for proper text extraction
        String extractedText = TextExtractor.extract(hwpFile, TextExtractMethod.InsertControlTextBetweenParagraphText);

        if (extractedText == null || extractedText.trim().isEmpty()) {
            throw new IOException("No text content found in HWP file");
        }

        return extractedText.trim();
    }

    /**
     * Validate HWP file format (extension + magic bytes)
     *
     * Security: Validates both extension and file signature to prevent malicious file uploads
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

        // Security: Validate HWP magic bytes (prevents file extension spoofing)
        // HWP files use OLE2/CFBF format with signature: D0 CF 11 E0 A1 B1 1A E1
        try (InputStream is = file.getInputStream()) {
            byte[] header = new byte[8];
            int read = is.read(header);

            if (read < 8) {
                log.warn("File too small to be valid HWP: {} bytes", read);
                return false;
            }

            // Validate OLE2/CFBF magic bytes
            if (header[0] != (byte)0xD0 || header[1] != (byte)0xCF ||
                header[2] != (byte)0x11 || header[3] != (byte)0xE0 ||
                header[4] != (byte)0xA1 || header[5] != (byte)0xB1 ||
                header[6] != (byte)0x1A || header[7] != (byte)0xE1) {

                log.warn("Invalid HWP magic bytes for file: {}", filename);

                // Check if it's an executable or other dangerous file type
                if (header[0] == (byte)0x4D && header[1] == (byte)0x5A) {
                    log.error("Detected Windows executable disguised as HWP: {}", filename);
                    return false;
                } else if (header[0] == (byte)0x7F && header[1] == (byte)0x45 &&
                          header[2] == (byte)0x4C && header[3] == (byte)0x46) {
                    log.error("Detected ELF executable disguised as HWP: {}", filename);
                    return false;
                } else if (header[0] == (byte)0x50 && header[1] == (byte)0x4B &&
                          header[2] == (byte)0x03 && header[3] == (byte)0x04) {
                    log.error("Detected ZIP file disguised as HWP: {}", filename);
                    return false;
                }

                return false;
            }

            return true;

        } catch (IOException e) {
            log.error("Error validating HWP file: {}", e.getMessage());
            return false;
        }
    }
}
