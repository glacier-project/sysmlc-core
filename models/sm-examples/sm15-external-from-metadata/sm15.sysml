package SM15Rep {
    metadata def ExternalModule {
        attribute lang : String;
        attribute files : String[*];
    }

    @ExternalModule {
        lang = "python";
        files = ("models/sm-examples/sm15-external-from-metadata/ramp.py");
    }

    private import ScalarValues::*;
    private import SI::*;
    package P { calc def step { in x : Real; in dt : Real; return : Real; } }
    state def Ramp {
        attribute x : Real := 0.0;
        entry; then run;
        state run;
        transition first run
            accept after 0.1 [s]
            do assign x := P::step(x, 0.1)
            then run;
    }
}
