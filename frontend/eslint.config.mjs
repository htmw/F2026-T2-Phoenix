import coreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

// eslint-config-next ships native flat configs, so no eslintrc compatibility layer.
const config = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts", "scripts/**"],
  },
  ...coreWebVitals,
  ...nextTypescript,
  {
    rules: {
      // Office data loads in effects and writes state when the response arrives.
      "react-hooks/set-state-in-effect": "off",
    },
  },
];

export default config;
