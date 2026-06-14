package sysmlc {
    private import ScalarValues::*;

    // Utility functions; each backend maps these to target code, like
    // NumericalFunctions::abs. Invoked in expression positions.
    calc def print { in msg; }
    calc def log { in tag; in value; }
}
