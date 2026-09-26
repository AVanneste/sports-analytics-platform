import React from "react";
import ReactDOMServer from "react-dom/server";
import App from "./src/App";
const data = JSON.parse(fs.readFileSync("./public/data/sports_data.json", "utf-8"));
global.fetch = () => Promise.resolve({
  ok: true,
  json: () => Promise.resolve(data)
});
try {
  const html = ReactDOMServer.renderToString(React.createElement(App));
  console.log("RENDER SUCCESS, html length:", html.length);
} catch (e) {
  console.error("RENDER ERROR:", e);
}
