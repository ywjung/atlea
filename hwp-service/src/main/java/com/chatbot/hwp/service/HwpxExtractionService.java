package com.chatbot.hwp.service;

import com.chatbot.hwp.model.DocumentExtractionResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.w3c.dom.Document;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.util.*;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

@Slf4j
@Service
public class HwpxExtractionService {

    private static final long MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
    private static final List<String> ALLOWED_EXTENSIONS = List.of(".hwpx");

    /**
     * Validate if the file is a valid HWPX file
     */
    public boolean isValidHwpxFile(MultipartFile file) {
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

        return true;
    }

    /**
     * Extract text from HWPX file
     */
    public DocumentExtractionResponse extractText(MultipartFile file) {
        long startTime = System.currentTimeMillis();
        String filename = file.getOriginalFilename();

        try {
            log.info("Extracting text from HWPX: {}", filename);
            byte[] fileBytes = file.getBytes();

            return extractTextFromBytes(fileBytes, filename, startTime);
        } catch (Exception e) {
            log.error("Failed to read file bytes: {}", e.getMessage());
            return buildErrorResponse(filename, "Failed to read file", startTime);
        }
    }

    /**
     * Extract text from base64-encoded HWPX
     */
    public DocumentExtractionResponse extractTextFromBase64(String base64Content, String filename) {
        long startTime = System.currentTimeMillis();

        try {
            log.info("Extracting text from base64 HWPX: {}", filename);
            byte[] fileBytes = Base64.getDecoder().decode(base64Content);

            return extractTextFromBytes(fileBytes, filename, startTime);
        } catch (IllegalArgumentException e) {
            log.error("Invalid base64 encoding: {}", e.getMessage());
            return buildErrorResponse(filename, "Invalid base64 encoding", startTime);
        }
    }

    /**
     * Core extraction logic from byte array
     */
    private DocumentExtractionResponse extractTextFromBytes(byte[] fileBytes, String filename,
                                                            long startTime) {
        try {
            String text = extractTextFromHwpx(fileBytes);

            long processingTime = System.currentTimeMillis() - startTime;

            log.info("Successfully extracted {} characters from HWPX in {}ms",
                    text.length(), processingTime);

            return DocumentExtractionResponse.builder()
                    .text(text)
                    .success(true)
                    .filename(filename)
                    .fileType("HWPX")
                    .processingTimeMs(processingTime)
                    .build();
        } catch (Exception e) {
            log.error("Failed to extract text from HWPX: {}", e.getMessage());
            return buildErrorResponse(filename, "HWPX extraction failed", startTime);
        }
    }

    /**
     * Extract text from HWPX file (ZIP-based XML format)
     */
    private String extractTextFromHwpx(byte[] fileBytes) throws Exception {
        StringBuilder text = new StringBuilder();
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        DocumentBuilder builder = factory.newDocumentBuilder();

        try (ZipInputStream zis = new ZipInputStream(new ByteArrayInputStream(fileBytes))) {
            ZipEntry entry;

            // HWPX files contain section XML files in Contents/ directory
            while ((entry = zis.getNextEntry()) != null) {
                String entryName = entry.getName();

                // Extract text from section XML files
                if (entryName.startsWith("Contents/section") && entryName.endsWith(".xml")) {
                    log.debug("Processing HWPX section: {}", entryName);

                    // Read XML content
                    byte[] xmlBytes = readZipEntry(zis);

                    // Parse XML and extract text
                    Document doc = builder.parse(new ByteArrayInputStream(xmlBytes));
                    String sectionText = extractTextFromXml(doc);

                    if (!sectionText.trim().isEmpty()) {
                        text.append(sectionText).append("\n\n");
                    }
                }

                zis.closeEntry();
            }
        }

        return text.toString();
    }

    /**
     * Read entire zip entry content
     */
    private byte[] readZipEntry(InputStream zis) throws Exception {
        byte[] buffer = new byte[8192];
        int bytesRead;
        java.io.ByteArrayOutputStream baos = new java.io.ByteArrayOutputStream();

        while ((bytesRead = zis.read(buffer)) != -1) {
            baos.write(buffer, 0, bytesRead);
        }

        return baos.toByteArray();
    }

    /**
     * Extract text from XML document
     */
    private String extractTextFromXml(Document doc) {
        StringBuilder text = new StringBuilder();

        // HWPX text is stored in <hp:t> (text) elements
        NodeList textNodes = doc.getElementsByTagName("hp:t");

        for (int i = 0; i < textNodes.getLength(); i++) {
            Node node = textNodes.item(i);
            String nodeText = node.getTextContent();

            if (nodeText != null && !nodeText.trim().isEmpty()) {
                text.append(nodeText);
            }
        }

        // Also check for <t> elements (some HWPX variations)
        NodeList altTextNodes = doc.getElementsByTagName("t");
        for (int i = 0; i < altTextNodes.getLength(); i++) {
            Node node = altTextNodes.item(i);
            String nodeText = node.getTextContent();

            if (nodeText != null && !nodeText.trim().isEmpty()) {
                text.append(nodeText);
            }
        }

        return text.toString();
    }

    /**
     * Build error response
     */
    private DocumentExtractionResponse buildErrorResponse(String filename, String errorMessage, long startTime) {
        return DocumentExtractionResponse.builder()
                .text("")
                .success(false)
                .error(errorMessage)
                .filename(filename)
                .fileType("HWPX")
                .processingTimeMs(System.currentTimeMillis() - startTime)
                .build();
    }
}
