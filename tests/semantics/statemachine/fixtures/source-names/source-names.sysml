package SourceNames {
    state def Machine {
        entry; then 'S.1';
        state 'S.1';
        state 'Out"er' {
            entry; then 'a\\b';
            state 'a\\b';
            state 'it\'s';
            transition first 'a\\b' then 'it\'s';
        }
        transition first 'S.1' then 'Out"er';
    }
}
