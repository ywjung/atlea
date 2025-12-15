# Multi-stage build for HWP Service
FROM maven:3.9-eclipse-temurin-17 AS builder

WORKDIR /app

# Copy pom.xml and download dependencies
COPY pom.xml .
RUN mvn dependency:go-offline

# Copy source code and build
COPY src ./src
RUN mvn clean package -DskipTests

# Runtime stage
FROM eclipse-temurin:17-jre-alpine

WORKDIR /app

# Install required fonts for HWP processing
RUN apk add --no-cache \
    fontconfig \
    ttf-dejavu \
    msttcorefonts-installer \
    && update-ms-fonts

# Copy JAR from builder
COPY --from=builder /app/target/*.jar app.jar

# Create directory for temporary files
RUN mkdir -p /tmp

# Expose port
EXPOSE 8081

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8081/api/hwp/health || exit 1

# Run application
ENTRYPOINT ["java", "-jar", "app.jar"]
