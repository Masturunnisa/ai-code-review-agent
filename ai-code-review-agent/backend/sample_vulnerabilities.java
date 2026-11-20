class VulnerableExample {
    String password = "local-test-secret-only";

    java.sql.ResultSet lookup(java.sql.Connection connection, String name) throws Exception {
        java.sql.Statement statement = connection.createStatement();
        return statement.executeQuery("SELECT * FROM users WHERE name = '" + name + "'");
    }

    void runCommand(String argument) throws Exception {
        Runtime.getRuntime().exec(argument);
    }
}
