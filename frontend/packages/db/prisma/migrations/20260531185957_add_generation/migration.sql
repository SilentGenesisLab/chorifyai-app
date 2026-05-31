-- CreateTable
CREATE TABLE "generations" (
    "id" TEXT NOT NULL,
    "module" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "text" TEXT,
    "voiceName" TEXT,
    "resultUrl" TEXT,
    "thumbnailUrl" TEXT,
    "durationSec" INTEGER,
    "orgId" TEXT NOT NULL,
    "createdById" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "generations_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "generations_orgId_createdAt_idx" ON "generations"("orgId", "createdAt");

-- AddForeignKey
ALTER TABLE "generations" ADD CONSTRAINT "generations_orgId_fkey" FOREIGN KEY ("orgId") REFERENCES "organizations"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "generations" ADD CONSTRAINT "generations_createdById_fkey" FOREIGN KEY ("createdById") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
