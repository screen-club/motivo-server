#!/bin/sh
# Configure s3cmd
cat > ~/.s3cfg << EOF
host_base = ${S3_ENDPOINT#*//}
host_bucket = ${S3_ENDPOINT#*//}
access_key = ${S3_ACCESS_KEY}
secret_key = ${S3_SECRET_KEY}
use_https = true
EOF
echo "🔧 S3 configuration completed"

while true; do
    # Create timestamp
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    echo "⏰ Starting backup at ${TIMESTAMP}"

    # Create tar.gz archive excluding cache directory and dataset directory
    cd /backup
    echo "📦 Creating archive (excluding cache and dataset)..."
    tar --exclude='storage/cache'  --exclude='storage/model' --exclude='datasets' -czf storage_${TIMESTAMP}.tar.gz storage/

    # Upload to S3
    echo "☁️  Uploading to S3..."
    s3cmd put storage_${TIMESTAMP}.tar.gz s3://${BACKUP_BUCKET}/backups/storage_${TIMESTAMP}.tar.gz

    # Remove local archive
    echo "🧹 Cleaning up local archive..."
    rm storage_${TIMESTAMP}.tar.gz

    echo "✅ Backup completed successfully"

    # Sleep for specified interval
    echo "💤 Sleeping for ${BACKUP_INTERVAL_HOURS} hours"
    sleep $(expr ${BACKUP_INTERVAL_HOURS} \* 3600)
done
