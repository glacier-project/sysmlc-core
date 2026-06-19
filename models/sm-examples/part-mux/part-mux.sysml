// A hub sends M via one of two ports. Same-name routing would fan M out to
// BOTH sinks (both accept M); port-based routing sends it only to the sink
// connected via the sending port.
package PartMux {
    item def M;

    state def HubBehavior {
        port a;
        port b;
        entry; then run;
        state run;
        state sent;
        transition first run do send new M() via a then sent;
    }
    state def SinkBehavior {
        port p;
        entry; then waiting;
        state waiting;
        state got;
        transition first waiting accept M via p then got;
    }

    part def Hub   { port a; port b; exhibit state : HubBehavior; }
    part def Sink1 { port p; exhibit state : SinkBehavior; }
    part def Sink2 { port p; exhibit state : SinkBehavior; }

    part mux {
        part hub : Hub;
        part s1 : Sink1;
        part s2 : Sink2;
        connect hub.a to s1.p;
        connect hub.b to s2.p;
    }
}
