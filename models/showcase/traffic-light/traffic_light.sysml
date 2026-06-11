package TrafficLight {
    private import ScalarValues::*;
    private import SI::*;
    private import ISQ::DurationValue;

    enum def LightColor :> String {
        enum red = "red";
        enum green = "green";
        enum yellow = "yellow";
    }

    item def PedestrianRequest;

    state def TrafficLight {
        attribute color : LightColor := LightColor::red;
        attribute requested : Boolean := false;

        entry;
            then showRed;

        state showRed {
            entry action {
                assign color := LightColor::red;
                assign requested := false;
            }
        }
        state showGreen {
            entry assign color := LightColor::green;
        }
        state showYellow {
            entry assign color := LightColor::yellow;
        }

        transition first showRed accept after 4 [s] then showGreen;
        transition first showGreen
            accept PedestrianRequest
            do assign requested := true
            then showYellow;
        transition first showGreen accept after 6 [s] then showYellow;
        transition first showYellow accept after 2 [s] then showRed;
    }
}
