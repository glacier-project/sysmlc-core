package sysmlc {
    private import ScalarValues::*;

    // Utility actions used as side-effecting transition effects.
    action def print { in msg; }
    action def log { in tag; in value; }
}
