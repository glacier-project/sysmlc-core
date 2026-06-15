package PartZero {
    part def Widget { port p; }          // no exhibit -> pure composite

    part sys {                           // top-level usage
        part w : Widget;
    }
}
