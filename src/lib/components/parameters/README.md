# Parameters Components

This directory contains components for managing environment parameters in the application.

## Components

### ParameterPanel.svelte
The main panel for displaying and editing environment parameters. Features:
- Controls for basic physics parameters like gravity and density
- Wind control parameters
- Additional simulation parameters
- Reset buttons for parameters and simulation

### ParameterControl.svelte
Versatile control component for handling different parameter types:
- Range sliders for numerical values
- Select dropdowns for options
- Checkboxes for boolean values
- Auto-configuration from parameter metadata

### ParameterGroup.svelte
Container component for organizing related parameters:
- Optional group title
- Grid layout with configurable columns
- Consistent spacing and styling

### ParameterEnvelopeButton.svelte
Button component for editing parameter envelopes:
- Connects to the currentParamName store
- Triggers envelope editor for a specific parameter

## State Management
Parameters state is managed through:
- parameterStore for local state management and persistence
- WebSocket communication to sync with the server

## Usage
These components work together to provide a complete parameter management system:
1. ParameterPanel uses ParameterGroup to organize related controls
2. ParameterControl provides the individual controls for each parameter
3. Changes are propagated through the parameterStore
4. The server is updated with parameter changes via WebSocket