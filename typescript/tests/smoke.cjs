const { AGS_VERSION, graphDigest } = require("../dist/index.cjs");

if (AGS_VERSION !== "1.0" || !graphDigest({}).startsWith("sha256-")) process.exit(1);
