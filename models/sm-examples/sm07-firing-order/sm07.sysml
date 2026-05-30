package SM07 {
    private import ScalarValues::*;

    state def MachineFiringOrder {
        attribute seq : Integer := 0;
        attribute exitAt : Integer := 0;
        attribute effectAt : Integer := 0;
        attribute entryAt : Integer := 0;

        entry;
            then a;
        state a {
            exit action {
                assign seq := seq + 1;
                assign exitAt := seq;
            }
        }
        state b {
            entry action {
                assign seq := seq + 1;
                assign entryAt := seq;
            }
        }
        transition first a do action {
            assign seq := seq + 1;
            assign effectAt := seq;
        } then b;
    }
}
