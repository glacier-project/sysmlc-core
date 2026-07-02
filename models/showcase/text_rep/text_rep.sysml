package TextRepExample {
    private import ScalarValues::*;

    attribute def Point {
        attribute x : Integer;
        attribute y : Integer;
    }

    calc def addOne {
        in value : Integer;
        return : Integer;

        rep impl langauge "Python"
        /*
         *  def addOne(val):
         *      return val+1
        */
    }
}
