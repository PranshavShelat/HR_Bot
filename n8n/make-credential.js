// Turns a Google service account key file into an n8n credential import file.
// n8n encrypts the credential data with its own key when importing it.
// Usage: node make-credential.js <service-account.json> <output.json>
const fs = require("fs");

const [keyPath, outPath] = process.argv.slice(2);
const key = JSON.parse(fs.readFileSync(keyPath, "utf8"));

const credential = {
  id: "hrSheetsServAcc1",
  name: "Google Sheets service account",
  type: "googleApi",
  data: {
    region: "global",
    email: key.client_email,
    privateKey: key.private_key,
    inpersonate: false,
    httpNode: false,
  },
};

fs.writeFileSync(outPath, JSON.stringify([credential]), { mode: 0o600 });
console.log(`Prepared Sheets credential for ${key.client_email}`);
