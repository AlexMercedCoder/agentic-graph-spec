import { AGS_VERSION, graphDigest } from "../dist/index.js";

if (AGS_VERSION !== "1.0" || !graphDigest({}).startsWith("sha256-")) process.exit(1);
