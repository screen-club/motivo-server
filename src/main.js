import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";
import { Router } from "svelte-routing";

mount(App, {
  target: document.body,
  props: {
    url: window.location.pathname,
  },
});

export default App;
